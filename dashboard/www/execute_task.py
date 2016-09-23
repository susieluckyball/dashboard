# import random
# import subprocess
# from flask import Flask, request, render_template, session, flash, redirect, \
#     url_for, jsonify
    
# from . import celery
# from . import main

# # @celery.task
# # def execute_command(command):
# #     # logging.info("Executing command in Celery " + command)
# #     try:
# #         subprocess.check_call(command, shell=True)
# #     except subprocess.CalledProcessError as e:
# #         logging.error(e)
# #         raise 



# # @main.route('/runtask', methods=['POST'])
# # def execute_async(key, command):
# # 	# celery queueing the task
# #     task = execute_command.apply_async(args=[command])
# #     return jsonify({}), 202, {'Location': url_for('taskstatus',
# #                                                   task_id=task.id)}


# @celery.task(bind=True)
# def long_task(self):
#     """Background task that runs a long function with progress reports."""
#     verb = ['Starting up', 'Booting', 'Repairing', 'Loading', 'Checking']
#     adjective = ['master', 'radiant', 'silent', 'harmonic', 'fast']
#     noun = ['solar array', 'particle reshaper', 'cosmic ray', 'orbiter', 'bit']
#     message = ''
#     total = random.randint(10, 50)
#     for i in range(total):
#         if not message or random.random() < 0.25:
#             message = '{0} {1} {2}...'.format(random.choice(verb),
#                                               random.choice(adjective),
#                                               random.choice(noun))
#         self.update_state(state='PROGRESS',
#                           meta={'current': i, 'total': total,
#                                 'status': message})
#         time.sleep(1)
#     return {'current': 100, 'total': 100, 'status': 'Task completed!',
#             'result': 42}


# @main.route('/longtask', methods=['POST'])
# def longtask():
#     task = long_task.apply_async()
#     return jsonify({}), 202, {'Location': url_for('taskstatus',
              


# @main.route('/status/<task_id>')
# def taskstatus(task_id):
#     task = long_tast.AsyncResult(task_id)
#     if task.state == 'PENDING':
#         response = {
#             'state': task.state,
#             'current': 0,
#             'total': 1,
#             'status': 'Pending...'
#         }
#     elif task.state != 'FAILURE':
#         response = {
#             'state': task.state,
#             'current': task.info.get('current', 0),
#             'total': task.info.get('total', 1),
#             'status': task.info.get('status', '')
#         }
#         if 'result' in task.info:
#             response['result'] = task.info['result']
#     else:
#         # something went wrong in the background job
#         response = {
#             'state': task.state,
#             'current': 1,
#             'total': 1,
#             'status': str(task.info),  # this is the exception raised
#         }
#     return jsonify(response)