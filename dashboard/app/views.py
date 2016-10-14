from flask import Flask, request, render_template, redirect, flash, url_for, jsonify, session
from flask.ext.wtf import Form 
from flask_login import login_user, logout_user, login_required
from wtforms import (BooleanField, PasswordField, SelectField, StringField, 
                    SubmitField, TextAreaField, TextField)
from wtforms.validators import DataRequired, Email, EqualTo, Length, Required

from app import main, auth, login_manager
from models import RequestHandler

class JobForm(Form):
    name = TextField('Name',  validators=[DataRequired()])
    timezone = SelectField('Timezone', coerce=str, choices=[("US/Eastern","US/Eastern"), 
            ("US/Central","US/Central"), ("Europe/London","Europe/London")], 
            validators=[DataRequired()])
    start_dt = TextField('Start Datetime (default now)')
    end_dt = TextField('End Datetime (default None)')
    schedule_interval = TextField('Run Interval (seconds)')
    operator = SelectField('Operator', coerce=str, choices=[("bash", "Bash"),
            ("python", "Python"), ("sql", "SQL")])
    tags = TextField('Tags', default='')
    command = TextAreaField('Command', validators=[DataRequired()],
                render_kw={"rows":5, "cols":80})
    submit = SubmitField('submit', render_kw={"class":"btn btn-primary"})

    def add_placeholder(self, job, tags):
        for field in self:
            if field.type in ('CSRFTokenField', 'HiddenField'):
                continue
            if field.name not in ('tags', 'submit'):
                setattr(field, "data", getattr(job, field.name))
            elif field.name == 'tags':
                setattr(field, "data", ','.join(tags))

class LoginForm(Form):
    email = StringField('Email', validators=[DataRequired(), Email()]) 
    password = PasswordField('Password', validators=[DataRequired()]) 
    remember_me = BooleanField('Keep me logged in')
    submit = SubmitField('Log In')

class RegistrationForm(Form):
    email = StringField('Email', validators=[DataRequired(), Length(1, 64), Email()])
    password = PasswordField('Password', validators=[DataRequired(), EqualTo('password2', message='Passwords must match.')])
    password2 = PasswordField('Confirm password', validators=[DataRequired()])
    submit = SubmitField('Register')

    def validate_email(self, field):
        # if User.query.filter_by(email=field.data).first():
        if RequestHandler.get_user(email=field.data):
            raise ValidationError('Email already registered.')


@main.route('/', methods=['GET', 'POST'])
@main.route('/index', methods=['GET', 'POST'])
def index():
    all_tags = [item[0] for item in RequestHandler.get_tags()]
    all_active_jobs = RequestHandler.get_jobs(only_active=False)
    running_tasks = RequestHandler.info_tasks(only_running=True)
    for job in all_active_jobs:
        job.initialize_shortcommand()
        job.get_local_run_time()
    return render_template('index.html', 
                all_tags=all_tags,
                all_active_jobs=all_active_jobs,
                running_tasks=running_tasks)


@main.route('/jobs/new', methods=['GET', 'POST'])
def add_job():
    form = JobForm()
    if request.method == 'POST':
        if form.validate():
            job_args = {k: v for k, v in request.form.items() if k != 'tags'}
            if len(request.form['tags']) == 0:
                tags = ["no-tag"]
            else:
                tags = [t.strip() for t in request.form['tags'].split(",")]
                
            added = RequestHandler.add_job(job_args, tags)
            if added:
                flash("Job create request for job name {}".format(request.form["name"]), "success")
                return redirect(url_for('main.index'))
            else:
                flash("Job with name {} exists, do you want to edit this job?".format(request.form["name"]), 
                    "warning")
                return redirect(url_for('main.edit_job', job_name=form.name.data))
        else:
            flash("Error: job name and command are required.")
    return render_template('add_job.html', form=form, modify=False)


@main.route('/jobs/edit/<job_name>', methods=['GET', 'POST'])
def edit_job(job_name):
    current_job, tags, _ = RequestHandler.info_job(job_name)
    if current_job is None:
        # must be a bug...
        flash("Bug: job {} does not exist".format(job_name))
        return jsonify({})
    form = JobForm()
    form.add_placeholder(current_job, tags)
    form.name.render_kw = {'disabled': True}
    if request.method == 'POST':
        if form.validate():
            job_args = {k: v for k, v in request.form.items() if k != 'tags'}
            job_args['name'] = current_job.name
            if len(request.form['tags']) == 0:
                tags = ["no-tag"]
            else:
                tags = [t.strip() for t in request.form['tags'].split(",")]
            if RequestHandler.edit_job(job_args, tags):
                flash("Edited job {}".format(request.form['name']), "success")
            return redirect(url_for('main.index'))
        else:
            flash("Error: job name and command are required.")
    return render_template('add_job.html', form=form, modify=True)


@main.route('/jobs/<job_name>/<action>', methods=['GET', 'POST'])
def info_job(job_name, action='info'):
    if action == 'info':
        job, tags, tasks = RequestHandler.info_job(job_name)
        job.initialize_shortcommand()
        job.get_local_run_time()
        tasks = tasks[:min(10, len(tasks))]
        return render_template('job.html', job=job, 
                        tags=tags, tasks=tasks)
    elif action == 'run':
        flash("Force job {} to run now".format(job_name))
        celery_tid = RequestHandler.force_schedule_for_job(job_name)
    elif action == 'deactivate':
        msg = RequestHandler.change_job_status(job_name, deactivate=True)
        if msg is True:
            flash("Deactivated job {}".format(job_name))
        else:
            flash(msg)
    elif action == "activate":
        msg = RequestHandler.change_job_status(job_name, deactivate=False)
        if msg is True:
            flash("Activated job {}".format(job_name))
        else:
            flash(msg)
    elif action == 'edit':
        return redirect(url_for('main.edit_job', job_name=job_name))
    elif action == 'delete':
        flash("Job {} is deleted".format(job_name))
        RequestHandler.remove_job(job_name)
    return redirect(url_for('main.index'))

@main.route('/tags/<tag_name>', methods=['GET', 'POST'])
def info_tag(tag_name):
    jobs = RequestHandler.get_jobs_by_tag(only_active=False, tag_name=tag_name)
    return render_template('tag.html', tag_name=tag_name, jobs=jobs)


@main.route('/alerts', methods=['GET','POST'])
def subscribe_to_alert():
    pass
# @main.route('/jobs/tasks/<task_id>', methods=['GET'])
# def info_task(task_id):
#     task = RequestHandler.check_task_stdout(task_id)
#     if task is not None:
#         return jsonify({"output": task.result})
#     return jsonify({"Error": "cannot find the task..."})
         


@login_manager.user_loader
def load_user(id):
    return RequestHandler.get_user_by_id(id)


@auth.route('/login', methods=['GET', 'POST'])
def login():
    # Here we use a class of some kind to represent and validate our
    # client-side form data. For example, WTForms is a library that will
    # handle this for us, and we use a custom LoginForm to validate.
    form = LoginForm()
    if form.validate_on_submit():
        # Login and validate the user.
        # user should be an instance of your `User` class
        user = RequestHandler.get_user(form.email.data)
        if user is not None and user.verify_password(form.password.data):
            login_user(user, form.remember_me.data)
            flash('Logged in as {}.'.format(user.email))
            return redirect(request.args.get('next') or url_for('main.index'))
        flash("Invalid username or password")
    return render_template('auth/login.html', form=form)


@auth.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        RequestHandler.register(email=form.email.data, 
                            password=form.password.data)
        flash('You can now login.')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', form=form)


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('main.index'))
