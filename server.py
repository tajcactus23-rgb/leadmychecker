#!/usr/bin/env python3
"""
Lotterywest Backend Server
Connects UI to real Selenium scraper
"""

from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import threading
import queue
import json
import os
import sys
import time
from datetime import datetime

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__, static_folder='.')
socketio = SocketIO(app, cors_allowed_origins='*', ping_timeout=60, ping_interval=25)

# Import the checker
try:
    from lotterywest_checker import LotterywestChecker
    CHECKER_AVAILABLE = True
except Exception as e:
    print(f"Warning: Could not import checker: {e}")
    CHECKER_AVAILABLE = False

# Queue for background processing
task_queue = queue.Queue()
results = {}
running_tasks = {}

def process_task(task_id, email, password):
    """Process account check in background thread"""
    try:
        print(f"[{task_id}] Starting check for {email}")
        socketio.emit('status', {'task_id': task_id, 'status': 'running', 'message': 'Logging in...'})
        
        checker = LotterywestChecker()
        result = checker.check_account(email, password)
        
        # Store result
        results[task_id] = result
        
        # Emit result back to UI
        socketio.emit('result', {'task_id': task_id, 'result': result})
        
        if result.get('status') == 'VALID':
            socketio.emit('status', {'task_id': task_id, 'status': 'valid', 'message': f"Valid: {email}"})
        else:
            socketio.emit('status', {'task_id': task_id, 'status': 'failed', 'message': f"Failed: {email}"})
            
    except Exception as e:
        error_result = {'status': 'ERROR', 'email': email, 'error': str(e)}
        results[task_id] = error_result
        socketio.emit('result', {'task_id': task_id, 'result': error_result})
        socketio.emit('status', {'task_id': task_id, 'status': 'error', 'message': str(e)})

@app.route('/')
def index():
    return send_from_directory('.', 'lotterywest_ui.html')

@app.route('/check', methods=['POST'])
def check_account():
    """Check a single account"""
    data = request.get_json()
    email = data.get('email', '')
    password = data.get('password', '')
    task_id = data.get('task_id', f'task_{int(time.time())}')
    
    if not email or not password:
        return jsonify({'error': 'Missing email or password'}), 400
    
    # Run in background thread
    thread = threading.Thread(target=process_task, args=(task_id, email, password))
    thread.daemon = True
    thread.start()
    
    return jsonify({'task_id': task_id, 'status': 'queued'})

@app.route('/check/batch', methods=['POST'])
def check_batch():
    """Check multiple accounts"""
    data = request.get_json()
    accounts = data.get('accounts', [])
    task_ids = []
    
    for i, account in enumerate(accounts):
        email = account.get('email', '')
        password = account.get('password', '')
        task_id = account.get('task_id', f'task_{i}_{int(time.time())}')
        
        if email and password:
            task_ids.append(task_id)
            thread = threading.Thread(target=process_task, args=(task_id, email, password))
            thread.daemon = True
            thread.start()
    
    return jsonify({'task_ids': task_ids, 'status': 'queued'})

@app.route('/result/<task_id>')
def get_result(task_id):
    """Get result for a task"""
    result = results.get(task_id)
    if result:
        return jsonify(result)
    return jsonify({'status': 'pending'}), 202

@socketio.on('check_account')
def handle_check(data):
    """SocketIO: Check account"""
    email = data.get('email')
    password = data.get('password')
    task_id = data.get('task_id', f'task_{int(time.time())}')
    
    if not email or not password:
        emit('error', {'message': 'Missing credentials'})
        return
    
    thread = threading.Thread(target=process_task, args=(task_id, email, password))
    thread.daemon = True
    thread.start()
    
    emit('queued', {'task_id': task_id})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting Lotterywest Backend on port {port}...")
    socketio.run(app, host='0.0.0.0', port=port, debug=False)