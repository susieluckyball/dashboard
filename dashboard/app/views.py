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
    command = TextAreaField('Command', validators=[DataRequired()])
    # placeholder should add tags
    submit = SubmitField('submit')


@main.route('/', methods=['GET', 'POST'])
@main.route('/index', methods=['GET', 'POST'])
def index():
    all_jobs = RequestHandler.info_all_jobs()
    running_tasks = RequestHandler.info_running_tasks()
    return render_template('index.html', 
                active_jobs=all_jobs["active"],
                running_tasks=running_tasks)

@main.route('/jobs/new', methods=['GET', 'POST'])
def add_job():
    form = JobForm()
    if request.method == 'POST':
        if form.validate():
            flash("Job create request for job name {}".format(request.form["name"]), "success")
            RequestHandler.add_job(request.form)
            return redirect(url_for('main.index'))
        else:
            flash("Error: job name and command are required.")
    return render_template('add_job.html', form=form)

@main.route('/jobs/<job_name>', methods=['GET', 'POST'])
def info_job(job_name):
    action = request.args.get("action")
    if action is None:
        job, tasks = RequestHandler.info_job(job_name)
        tasks = tasks[:min(5, len(tasks))]
        return render_template('job.html', job=job, tasks=tasks)
    elif action == 'run':
        flash("Force job {} to run now".format(job_name))
        celery_tid = RequestHandler.force_schedule_for_job(job_name)
        flash("Celery task id: {}".format(celery_tid))
    elif action == 'deactivate':
        msg = RequestHandler.deactivate_job(job_name)
        if msg is True:
            flash("Deactivated job {}".format(job_name))
        else:
            flash(msg)
    elif action == 'tag':
        flash(action)
    elif action == 'delete':
        flash("Job {} is deleted".format(job_name))
        RequestHandler.remove_job(job_name)
    return redirect(url_for('main.index'))



@main.route('/jobs/tasks/<task_id>', methods=['GET'])
def info_task(task_id):
    task = RequestHandler.check_task_stdout(task_id)
    if task is not None:
        return jsonify({"output": task.result})
    return jsonify({"Error": "cannot find the task..."})
         

