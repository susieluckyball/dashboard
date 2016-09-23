import shlex
import subprocess
from flask import Flask, request, render_template, redirect, flash, url_for, jsonify
from flask.ext.wtf import Form 
from wtforms import TextField, SubmitField
from wtforms.validators import DataRequired
    
from app import celery
from app import main


class CommandForm(Form):
    cmd = TextField('Bash script',  validators=[DataRequired()])
    submit = SubmitField('submit')

@main.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        return render_template('index.html')
    return redirect(url_for('main.index'))

# @celery.task(bind=True)
# def long_task(self):
#     """Background task that runs a long function with progress reports."""
#     verb = ['Starting up', 'Booting', 'Repairing', 'Loading', 'Checking']
#     adjective = ['master', 'radiant', 'silent', 'harmonic', 'fast']
#     noun = ['solar array', 'particle reshaper', 'cosmic ray', 'orbiter', 'bit']
#     message = ''
#     total = random.randint(20, 50)
#     for i in range(total):
#         if not message or random.random() < 0.25:
#             message = '{0} {1} {2}...'.format(random.choice(verb),
#                                               random.choice(adjective),
#                                               random.choice(noun))
#         self.update_state(state='PROGRESS',
#                           meta={'current': i, 'total': total,
#                                 'status': message})
#         time.sleep(2)
#     return {'current': 100, 'total': 100, 'status': 'Task completed!',
#             'result': 42}


@celery.task(bind=True)
def execute_command(command):
    # logging.info("Executing command in Celery " + command)
    args = shlex.split(command)
    subprocess.check_call(args, shell=True)


@main.route('/status/<task_id>')
def taskstatus(task_id):
    task = long_task.AsyncResult(task_id)
    if task.state == 'PENDING':
        response = {
            'state': task.state,
            'current': 0,
            'total': 1,
            'status': 'Pending...'
        }
    elif task.state != 'FAILURE':
        response = {
            'state': task.state,
            'current': task.info.get('current', 0),
            'total': task.info.get('total', 1),
            'status': task.info.get('status', '')
        }
        if 'result' in task.info:
            response['result'] = task.info['result']
    else:
        # something went wrong in the background job
        response = {
            'state': task.state,
            'current': 1,
            'total': 1,
            'status': str(task.info),  # this is the exception raised
        }
    return jsonify(response)


# @main.route('/longtask', methods=['POST'])
# def longtask():
#     task = long_task.apply_async()
#     return jsonify({}), 202, {'Location': url_for('main.taskstatus',
#                                                   task_id=task.id)}

@main.route('/add_task', methods=['POST'])
def add_task():
    form = CommandForm(request.form)
    print("------")
    print(form.errors)
    print(request.form['command'])
    # if form.validate():
    cmd = request.form['command']
    flash('Input command: ' + cmd)
    task = execute_command.apply_async(args[cmd])

    return jsonify({}), 202, {'Location': url_for('main.taskstatus',
                                              task_id=task.id)}
