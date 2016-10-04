from flask import Flask, request, render_template, redirect, flash, url_for, jsonify, session
from flask.ext.wtf import Form 
from wtforms import TextField, SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired

from app import main
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
            ("python", "Python"), ("stored_proc", "Stored Procedure")])
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


@main.route('/', methods=['GET', 'POST'])
@main.route('/index', methods=['GET', 'POST'])
def index():
    all_tags = [item[0] for item in RequestHandler.get_tags()]
    all_active_jobs = RequestHandler.get_jobs(only_active=False)
    running_tasks = RequestHandler.info_tasks(only_running=True)
    for job in all_active_jobs:
        job.initialize_shortcommand()
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
                tags = ["None"]
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
    if request.method == 'POST':
        if form.validate():
            job_args = {k: v for k, v in request.form.items() if k != 'tags'}
            if len(request.form['tags']) == 0:
                tags = ["None"]
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
        tasks = tasks[:min(10, len(tasks))]
        return render_template('job.html', job=job, 
                        tags=tags, tasks=tasks)
    elif action == 'run':
        flash("Force job {} to run now".format(job_name))
        celery_tid = RequestHandler.force_schedule_for_job(job_name)
        flash("Celery task id: {}".format(celery_tid))
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


# @main.route('/jobs/tasks/<task_id>', methods=['GET'])
# def info_task(task_id):
#     task = RequestHandler.check_task_stdout(task_id)
#     if task is not None:
#         return jsonify({"output": task.result})
#     return jsonify({"Error": "cannot find the task..."})
         

