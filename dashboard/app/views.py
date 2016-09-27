from flask import Flask, request, render_template, redirect, flash, url_for, jsonify, session
from flask.ext.wtf import Form 
from wtforms import TextField, SelectField, SubmitField
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
    command = TextField('Command')
    # placeholder should add tags
    submit = SubmitField('submit')


@main.route('/', methods=['GET', 'POST'])
@main.route('/index', methods=['GET', 'POST'])
def index():
    return render_template('index.html')

@main.route('/edit_job', methods=['GET', 'POST'])
def edit_job_handler():
    if request.method == 'POST' and form.validate():
        flash("Job create request for job name {}".format(request.form["name"]), "success")
        RequestHandler.add_job(request.form)
        return redirect(url_for('main.index'))
    return render_template('edit_job.html', form=JobForm())


# @main.route('/info_job', methods=['GET'])
# def info_jobs_handler():
#     if request.method == 'GET':
         


# @main.route('/info_job/<job_name>', method=['GET'])
# def info_job_handler():