from flask import Flask, request, render_template, redirect, flash, url_for, jsonify, session
from flask.ext.wtf import Form 
from flask_login import login_user, logout_user, login_required, current_user
from functools import partial
import json
from wtforms import (BooleanField, PasswordField, SelectField, 
                    StringField, SubmitField, TextAreaField, TextField)
from wtforms.validators import (DataRequired, Email, EqualTo, 
                    Length, Required, ValidationError)


from app import main, auth, login_manager
from models import RequestHandler
from dashboard.utils.date import (cron_presets, valid_crontab_string)



class JobForm(Form):
    name = TextField('Name',  validators=[DataRequired()])
    timezone = SelectField('Timezone', coerce=str, choices=[
            ('US/Eastern','US/Eastern'), 
            ('US/Central','US/Central'), 
            ('Europe/London','Europe/London')], 
            validators=[DataRequired()])
    start_dt = TextField('Start Datetime (default now)', id='start_dt')
    end_dt = TextField('End Datetime (default None)')
    schedule_interval = SelectField('Schedule Frequency', 
            choices=[('@daily', 'Daily'),
                    ('@weekdaydaily', 'Weekday Daily'),
                    ('@hourly', 'Hourly'),
                    ('@weekly', 'Weekly'),
                    ('other', 'Other')],
            id='schedule_interval',
            validators=[DataRequired()])
    weekday_to_run = TextField('Specify weekdays to run (e.g. input 1,5,7 for Mon, Fri and Sun)')
    schedule_interval_crontab = TextField(('(Note: filling this will OVERWRITE previous selection) '
            'Specify run interval '
            'in crontab time format (e.g. 0 6 * * 1,3,5)'))
    reset_status_at = TextField('Reset Status to Unknown at',
                default='0:00', validators=[DataRequired()])
    operator = SelectField('Operator', coerce=str, 
            choices=[('bash', 'Bash'),
                     ('sql', 'SQL'),
                    ('python', 'Python')],
            validators=[DataRequired()], id='operator')
    database = SelectField('Database', coerce=str, 
            choices=[('ENTERPRISE', 'Enterprise'),
                    ('REFERENCE', 'Reference'),
                    ('VENDORREF', 'Vendor Reference'),
                    ('VENDOR', 'Vendor'),
                    ('VENDORQS', 'Vendor QS'),
                    ('STATARB', 'StatArb')])
    tags = TextField('Tags', default='')
    subscriptions = TextField('Subscribe to Alert', default='')
    command = TextAreaField('Command', validators=[DataRequired()],
                render_kw={"rows":5, "cols":80})
    submit = SubmitField('submit', render_kw={"class":"btn btn-primary"})

    def add_placeholder(self, job, tags, subscriptions):
        for field in self:
            if field.type in ('CSRFTokenField', 'HiddenField'):
                continue        
            if field.name == 'tags':
                setattr(field, 'data', ','.join(tags))
            elif field.name == 'subscriptions':
                setattr(field, 'data',  ','.join(subscriptions))
            elif field.name == 'schedule_interval':
                setattr(field, 'data', 'other')
            elif field.name == 'weekday_to_run':
                setattr(field, 'data', '')
            elif field.name == 'schedule_interval_crontab':
                setattr(field, 'data', job.schedule_interval)
            elif field.name == 'submit':
                continue
            else:
                setattr(field, 'data', getattr(job, field.name))

    @classmethod
    def validate_and_prepare_job_args(cls, request, job_args, tags, subscriptions):
        for k, v in request.form.items():
            if k in ('tags', 'subscriptions'):
                continue
            job_args[k] = v

        # split tags and subscriptions
        if len(request.form['tags']) == 0:
            tags.append("no-tag")
        else:
            tags.extend([t.strip() for t in request.form['tags'].split(',')])
        if len(request.form['subscriptions']):
            subscriptions.extend(
                [s.strip() for s in request.form['subscriptions'].split(',')])        

        # organize optional fields
        if job_args['schedule_interval_crontab'] != '':
            if not valid_crontab_string(job_args['schedule_interval_crontab']):
                flash('Schedule interval crontab has to be a valid crontab string')
                return False

        elif job_args['schedule_interval'] == 'other':
            try:
                weekday_to_run = [int(i.strip()) for i in job_args['weekday_to_run'].split(',')]
                assert all([i > 0 and i <= 7 for i in weekday_to_run])
            except:
                flash('Weekday-to-run has to be a list of weekdays (1-7)')
                return False

            job_args['weekday_to_run'] = weekday_to_run
        
        # validate
        for sub in subscriptions:
            if '@' not in sub:
                flash('Subscriptions must be email addresses.')
                return False
        return True 


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
        if RequestHandler.get_user(email=field.data):
            raise ValidationError('Email already registered.')

class BlockJobForm(Form):
    block_for = SelectField('Block for', coerce=str, 
                choices=[('1 day', '1 day'),
                        ('1 week', '1 week'),
                        ('other', 'other')])
    block_until = StringField('Block until datetime')
    message = TextAreaField('Message', render_kw={"rows":3, "cols":60})


def redirect_url():
    return request.args.get('next') or \
           request.referrer or \
           url_for('index')

@main.route('/', methods=['GET', 'POST'])
@main.route('/index', methods=['GET', 'POST'])
def index():
    all_tags = [item[0] for item in RequestHandler.get_tags()]
    all_active_jobs = RequestHandler.get_jobs(only_active=False)
    running_tasks = RequestHandler.info_tasks(only_running=True)
    for job in all_active_jobs:
        job.initialize_shortcommand()
        job.initialize_short_result()
    return render_template('index.html', 
                all_tags=all_tags,
                all_active_jobs=all_active_jobs,
                running_tasks=running_tasks)


@main.route('/jobs/new', methods=['GET', 'POST'])
def add_job():
    form = JobForm()
    if request.method == 'POST':
        if form.validate():
            job_args = {}
            tags = []
            subscriptions = []
            if JobForm.validate_and_prepare_job_args(
                        request, job_args, tags, subscriptions):
                added = RequestHandler.add_job(job_args, tags, subscriptions)
                if added:
                    flash("Job create request for job name {}".format(
                                request.form["name"]), "success")
                    return redirect(url_for('main.index'))
                else:
                    flash("Job with name {} exists, do you want to edit this job?".format(request.form["name"]), 
                        "warning")
                    return redirect(url_for('main.edit_job', job_name=form.name.data))
        else:
            flash("Error: {}".format(form.validate()))
    return render_template('add_job.html', form=form, modify=False)


@main.route('/jobs/edit/<job_name>', methods=['GET', 'POST'])
def edit_job(job_name):
    current_job, tags, _, _ = RequestHandler.info_job(job_name)

    if current_job is None:
        # must be a bug...
        flash("Bug: job {} does not exist".format(job_name))
        return jsonify({})
    subscriptions = RequestHandler.get_subscribed(inst_type='job',
        name=current_job.name)
    form = JobForm()
    form.add_placeholder(current_job, tags, subscriptions)
    form.name.render_kw = {'disabled': True}
    if request.method == 'POST':
        if form.validate():
            job_args = {}
            tags = []
            subscriptions = []
            if JobForm.validate_and_prepare_job_args(
                        request, job_args, tags, subscriptions):
                job_args['name'] = current_job.name
                if RequestHandler.edit_job(job_args, tags, subscriptions):
                    flash("Edited job {}".format(request.form['name']), 
                            "success")
                return redirect(url_for('main.index'))
        else:
            flash("Error: job name and command are required.")
    return render_template('add_job.html', form=form, modify=True)




@main.route('/block_job', methods=['POST'])
@login_required
def block_job():
    block_till = request.form['block_till']
    message = request.form['message']
    job_name = request.form['job_name']
    errors = []
    print(current_user.email)
    if RequestHandler.block_job_till(job_name, 
            block_till, message, current_user.email, errors):
        return json.dumps({'status':'OK'})
    return json.dumps({'status':'ERROR', 'msg': "\n".join(errors)})

@main.route('/operation_job', methods=['GET'])
@login_required
def job_operation():
    job_name = request.args.get('job_name')
    op = request.args.get('operation')
    redir = request.args.get('stay')
    if job_name:
        if op == 'clear':
            RequestHandler.clear_tasks_history(job_name)
        elif op == 'delete':
            RequestHandler.remove_job(job_name)
        elif op == 'run':
            RequestHandler.force_schedule_for_job(job_name)
        elif op == 'deactivate':
            msg = RequestHandler.change_job_status(job_name, deactivate=True)
            if msg is True:
                flash("Deactivated job {}".format(job_name))
            else:
                flash(msg)
        elif op == 'activate':
            msg = RequestHandler.change_job_status(job_name, deactivate=False)
            if msg is True:
                flash("Activated job {}".format(job_name))
            else:
                flash(msg)           
        if redir:
            return redirect(redirect_url())
        else:
            return json.dumps({'status':'OK'})
    return json.dumps({'status':'ERROR', 'msg':'Job name not given'})


@main.route('/jobs/<job_name>', methods=['GET', 'POST'])
def info_job(job_name):
    job, tags, tasks, alerts = RequestHandler.info_job(job_name)
    job.initialize_shortcommand()
    job.initialize_short_result()
    return render_template('job.html', job=job, 
                    tags=tags, tasks=tasks,
                    alerts=alerts, 
                    isinstance=isinstance,
                    str=unicode)

# @main.route('/jobs/<job_name>/<action>', methods=['GET', 'POST'])
# def info_job(job_name, action='info'):
#     if action == 'info':
#         job, tags, tasks, alerts = RequestHandler.info_job(job_name)
#         job.initialize_shortcommand()
#         job.initialize_short_result()
#         return render_template('job.html', job=job, 
#                         tags=tags, tasks=tasks,
#                         alerts=alerts, 
#                         isinstance=isinstance,
#                         str=unicode)
#     elif action == 'run':
#         flash("Force job {} to run now".format(job_name))
#         celery_tid = RequestHandler.force_schedule_for_job(job_name)
#         return redirect(url_for('main.info_job', job_name=job_name, action='info'))
#     elif action == 'deactivate':
#         msg = RequestHandler.change_job_status(job_name, deactivate=True)
#         if msg is True:
#             flash("Deactivated job {}".format(job_name))
#         else:
#             flash(msg)
#     elif action == "activate":
#         msg = RequestHandler.change_job_status(job_name, deactivate=False)
#         if msg is True:
#             flash("Activated job {}".format(job_name))
#         else:
#             flash(msg)
#     elif action == 'edit':
#         return redirect(url_for('main.edit_job', job_name=job_name))
#     elif action == 'delete':
#         flash("Job {} is deleted".format(job_name))
#         RequestHandler.remove_job(job_name)
#     return redirect(url_for('main.index'))


@main.route('/tags/<tag_name>', methods=['GET', 'POST'])
def info_tag(tag_name):
    email = request.args.get('email')
    if email is None:
        jobs = RequestHandler.get_jobs_by_tag(only_active=False, tag_name=tag_name)
        subscribe = RequestHandler.get_subscribed(inst_type='tag', name=tag_name)
        for job in jobs:
            job.initialize_shortcommand()
        return render_template('tag.html', tag_name=tag_name, 
                    jobs=jobs, emails=subscribe)
    else:
        return redirect(url_for('main.edit_tag_subscription',
            action='add', name=tag_name, email=email))


@main.route('/alerts/<inst_type>/<name>/<action>', methods=['GET'])
@login_required
def edit_subscription_for_current_user(inst_type, name, action='subscribe'):
    email = current_user.email 
    if action == 'subscribe':
        RequestHandler.subscribe(inst_type, name, email)
        flash("Subscribe {} to {} '{}'".format(email, inst_type, name))
    else:
        RequestHandler.unsubscribe(inst_type, name, email)
        flash("Unsubscribe {} to {} '{}'".format(email, inst_type, name))
    if inst_type == 'job':
        return redirect(url_for('main.info_job', job_name=name))
    else:
        return redirect(url_for('main.info_tag', tag_name=name))


@main.route('/tag_alerts/<action>/<name>/<email>', methods=['GET'])
def edit_tag_subscription(action, name, email):
    if action == 'remove':
        RequestHandler.unsubscribe(inst_type='tag', name=name, email=email)
    elif action == 'add':
        emails = [e.strip() for e in email.split(",")]
        for e in emails:
            RequestHandler.subscribe(inst_type='tag', name=name, email=e)
    return redirect(url_for('main.info_tag', tag_name=name))



################
# login features 
################

@login_manager.user_loader
def load_user(id):
    return RequestHandler.get_user_by_id(id)


@login_manager.unauthorized_handler
def unauthorized_callback():
    return json.dumps({'status':'ERROR','msg':'login required!'})


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
        flash('Registered, you are good to log in!')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', form=form)


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('main.index'))

