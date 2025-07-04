import os
import re
import subprocess
import json
from flask import Flask, jsonify, render_template, request
import logging
from multiprocessing import Process
import time
import socket
from flask_socketio import SocketIO, emit
import random
import requests
import sys
from flask_cors import CORS
from urllib.parse import unquote
from werkzeug.utils import secure_filename
used_ports = set()
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
def find_imports(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    imports = re.findall(r'^\s*(?:import\s+([^\s,]+)|from\s+([^\s,]+)\s+import)', content, re.MULTILINE)
    imports = [imp[0] or imp[1] for imp in imports]
    return imports

def is_installed(package):
    try:
        __import__(package)
        return True
    except ImportError:
        return False

@app.route('/')
def index():
    return render_template('appindex.html')

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0
def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def test_connection(port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)  # 设置超时时间为1秒
            s.bind(('localhost', port))
            s.listen(1)
            return True
    except:
        return False

def find_free_port():
    attempts = 0
    while attempts < 100:  # 限制尝试次数，防止无限循环
        port = random.randint(3002, 40000)
        if port not in used_ports and not is_port_in_use(port):
            if test_connection(port):
                used_ports.add(port)
                return port
        attempts += 1
        time.sleep(0.1)  # 短暂延迟，避免过于频繁的尝试
    raise Exception("无法找到可用端口")
def find_free_teamport():
    while True:
        port = random.randint(40001, 40030)
        if not is_port_in_use(port):
            return port
@app.route('/delete-project', methods=['DELETE'])
def delete_project():
    try:
        data = request.json
        project_name = unquote(data.get('project'))
        file_paths = unquote(data.get('filePath'))

        if file_paths != 'WorkFlow':
            workflow_dir = os.path.join(os.getcwd(), 'WorkFlow', file_paths)
        else:
            workflow_dir = os.path.join(os.getcwd(), 'WorkFlow')
        if file_paths == 'WorkTeam':
            workflow_dir = os.path.join(os.getcwd(), 'WorkTeam')
        
        file_path = os.path.join(workflow_dir, project_name)
        
        if os.path.exists(file_path):
            os.remove(file_path)
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Project not found'}), 404
    except Exception as e:
        app.logger.error(f"Error occurred while deleting project: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/start-new-instance', methods=['POST'])
def start_new_instance():
    port = find_free_port()
    p = Process(target=run_app, args=(port,))
    p.start()
    return jsonify({'status': f'Instance started on port {port}'})

def run_app(port):
    subprocess.run([sys.executable, "app.py", str(port)])

@app.route('/start-new-WorkTeam', methods=['POST'])
def start_new_workteam():
    data = request.json
    project_name = data.get('projectName')
    port = find_free_teamport()
    p = Process(target=run_workteam, args=(port, project_name))
    p.start()
    return jsonify({'status': f'Instance started on port {port}', 'port': port})

def run_workteam(port, project_name):
    subprocess.run([sys.executable, "workteam.py", str(port)])
    
@app.route('/get-history-projects')
def get_history_projects():
    try:
        workflow_dir = os.path.join(os.getcwd(), 'WorkFlow')
        if not os.path.exists(workflow_dir):
            return jsonify([])

        projects = []
        for root, dirs, files in os.walk(workflow_dir):
            folder_name = os.path.basename(root)
            if folder_name:  # 过滤根目录
                projects.append({'type': 'folder', 'name': folder_name})
            for f in files:
                if f.endswith('.json'):
                    projects.append({'type': 'file', 'name': f, 'folder': folder_name})

        return jsonify(projects)
    except Exception as e:
        app.logger.error(f"Error occurred while fetching history projects: {e}")
        return jsonify({'error': str(e)}), 500
@app.route('/get-workteam-projects')
def get_workteam_projects():
    try:
        workteam_dir = os.path.join(os.getcwd(), 'WorkTeam')
        if not os.path.exists(workteam_dir):
            return jsonify([])

        projects = [f for f in os.listdir(workteam_dir) if f.endswith('.json')]
        return jsonify(projects)
    except Exception as e:
        app.logger.error(f"Error occurred while fetching WorkTeam projects: {e}")
        return jsonify({'error': str(e)}), 500
# 后端代码
@app.route('/health-check')
def health_check():
    """健康检查端点"""
    return jsonify({'status': 'ok'})

def is_server_ready(port, max_retries=5, retry_interval=1):
    """检查服务器是否就绪"""
    for _ in range(max_retries):
        try:
            response = requests.get(f'http://127.0.0.1:{port}/health-check', timeout=1)
            if response.status_code == 200:
                return True
        except requests.ConnectionError:
            time.sleep(retry_interval)
    return False

def send_request_with_retry(url, data, max_retries=3, retry_delay=1):
    """带重试机制的请求发送"""
    for attempt in range(max_retries):
        try:
            response = requests.post(
                url,
                json=data,
                timeout=(5, 30),
                headers={
                    'Connection': 'close',
                    'Content-Type': 'application/json'
                }
            )
            response.raise_for_status()  # 抛出非 200 状态的异常
            return response
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            app.logger.warning(f"Attempt {attempt + 1} failed, retrying in {retry_delay} seconds... Error: {e}")
            time.sleep(retry_delay)
            if attempt == max_retries - 1:
                raise  # 最后一次重试后抛出异常

@app.route('/load-project')
def load_project():
    port = request.args.get('port')
    project_name = request.args.get('name')
    file_path = request.args.get('path')
    project_host = request.args.get('host', '')
    project_callsign = request.args.get('callsign', '')

    # 设置工作目录
    if file_path == 'WorkFlow':
        workflow_dir = os.path.join(os.getcwd(), 'WorkFlow')
    elif file_path == 'WorkTeam':
        workflow_dir = os.path.join(os.getcwd(), 'WorkTeam')
    else:
        workflow_dir = os.path.join(os.getcwd(), 'WorkFlow', file_path)
    
    project_path = os.path.join(workflow_dir, project_name)
    if not os.path.exists(project_path):
        return jsonify({'error': 'Project not found'}), 404

    try:
        # 读取项目数据
        with open(project_path, 'r', encoding='utf-8') as file:
            project_data = json.load(file)
            project_data['name'] = project_name
            project_data['path'] = file_path
            project_data['host'] = project_host
            project_data['callsign'] = project_callsign

        url = f'http://127.0.0.1:{port}/load-project'

        # 重试机制
        def send_request_with_retries(url, data, retries=5, delay=2):
            for attempt in range(retries):
                try:
                    response = requests.post(
                        url, 
                        json=data, 
                        timeout=(5, 30),
                        headers={'Connection': 'close'}
                    )
                    if response.status_code == 200:
                        return response
                except requests.exceptions.ConnectionError:
                    if attempt < retries - 1:
                        time.sleep(delay)
                    else:
                        raise

        # 发送请求
        response = send_request_with_retries(url, project_data)

        # 确保连接被正确关闭
        response.close()

        if response.status_code != 200:
            return jsonify({'error': f'Failed to load project to instance (Status: {response.status_code})'}), response.status_code

        return jsonify({'status': 'Project loaded successfully'})
    except requests.exceptions.ConnectionError as e:
        app.logger.error(f"Connection error: {e}")
        return jsonify({'error': 'Connection failed - Please check if the instance is running'}), 503
    except requests.exceptions.Timeout as e:
        app.logger.error(f"Timeout error: {e}")
        return jsonify({'error': 'Request timed out - Server might be busy'}), 504
    except Exception as e:
        app.logger.error(f"Error occurred while loading project: {e}")
        return jsonify({'error': str(e)}), 500

@socketio.on('connect')
def test_connect():
    emit('message', 'Connected to WebSocket')

if __name__ == '__main__':
    import sys

    # 接收可选端口参数
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    else:
        port = 3001

    # 找到一个可用端口
    while is_port_in_use(port):
        # 方案 A: 继续用 print
        print(f"Port {port} is already in use. Choosing another port.", flush=True)
        # 方案 B: 或者用 logger
        # logger.info("Port %d is already in use. Choosing another port.", port)
        port = find_free_port()

    # 通知启动
    print(f"Starting server on port {port}", flush=True)
    # logger.info("Starting server on port %d", port)

    # 显式指定 host，关闭 reloader
    socketio.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=True,
        use_reloader=False,
        # 如果你安装了 gevent-websocket，可指定 async_mode
        # async_mode='gevent',
    )
