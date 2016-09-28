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
    command = TextAreaField('Command')
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

@main.route('/edit_job', methods=['GET', 'POST'])
def edit_job():
    form = JobForm()
    if request.method == 'POST' and form.validate():
        flash("Job create request for job name {}".format(request.form["name"]), "success")
        RequestHandler.add_job(request.form)
        return redirect(url_for('main.index'))
    return render_template('edit_job.html', form=form)


@main.route('/info_task/<task_id>', methods=['GET'])
def info_task(task_id):
    task = RequestHandler.check_task_stdout(task_id)
    if task is not None:
        return jsonify({"output": task.result})
    return jsonify({})
         


@main.route('/info_job/<job_name>', methods=['GET'])
def info_job(job_name):
    job, tasks = RequestHandler.info_job(job_name)
    tasks = tasks[:min(5, len(tasks))]
    return render_template('job.html', job=job, tasks=tasks)

