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
import psutil
from datetime import datetime
from pathlib import Path

used_ports = set()
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 实例注册表（内存态）
instances_registry = {}
# instances_registry 结构：
# {
#   "port": {
#     "port": int,
#     "type": "app" | "workteam",
#     "project_name": str,
#     "status": "running" | "stopped" | "paused",
#     "pid": int | None,
#     "start_time": timestamp,
#     "last_heartbeat": timestamp
#   }
# }
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

@app.route('/control-room')
def control_room():
    """监控面板页面"""
    return render_template('control-room.html')

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

# ==================== 实例监控与管理接口 ====================

@app.route('/hub/register-instance', methods=['POST'])
def register_instance():
    """实例主动注册（由 app.py 或 workteam.py 启动时调用）"""
    data = request.json
    logger.info(f"[DEBUG] 收到注册请求: {data}")
    
    port = data.get('port')
    instance_type = data.get('type')  # 'app' or 'workteam'
    project_name = data.get('project_name', f'{instance_type}_{port}')
    pid = data.get('pid')
    
    instances_registry[str(port)] = {
        'port': port,
        'type': instance_type,
        'project_name': project_name,
        'status': 'running',
        'pid': pid,
        'start_time': datetime.now().timestamp(),
        'last_heartbeat': datetime.now().timestamp()
    }
    
    logger.info(f"✅ 实例注册成功: {instance_type} on port {port}, project={project_name}, pid={pid}")
    logger.info(f"[DEBUG] 当前注册表大小: {len(instances_registry)}")
    return jsonify({'status': 'registered', 'port': port})

@app.route('/hub/heartbeat', methods=['POST'])
def heartbeat():
    """实例心跳（app.py/workteam.py 定期发送）"""
    data = request.json
    port = str(data.get('port'))
    
    if port in instances_registry:
        instances_registry[port]['last_heartbeat'] = datetime.now().timestamp()
        instances_registry[port]['status'] = data.get('status', 'running')
        return jsonify({'status': 'ok'})
    
    return jsonify({'error': 'Instance not registered'}), 404

@app.route('/hub/instances', methods=['GET'])
def list_instances():
    """列出所有实例及状态"""
    logger.info(f"[DEBUG] 收到实例列表请求")
    logger.info(f"[DEBUG] 当前注册表大小: {len(instances_registry)}")
    
    # 检查端口是否仍在监听，自动清理已停止的实例
    active_instances = {}
    stopped_ports = []
    
    for port_str, info in list(instances_registry.items()):
        port = info['port']
        logger.info(f"[DEBUG] 检查端口 {port}")
        
        is_active = is_port_in_use(port)
        is_process_alive = False
        
        # 检查进程是否存活
        if info.get('pid'):
            try:
                process = psutil.Process(info['pid'])
                is_process_alive = process.is_running()
                logger.info(f"[DEBUG] 端口 {port} - 进程 {info['pid']} 存活: {is_process_alive}")
            except psutil.NoSuchProcess:
                is_process_alive = False
                logger.info(f"[DEBUG] 端口 {port} - 进程 {info['pid']} 不存在")
        
        # 检查心跳超时（超过 60 秒没有心跳视为离线）
        last_heartbeat = info.get('last_heartbeat', 0)
        heartbeat_timeout = (datetime.now().timestamp() - last_heartbeat) > 60
        
        if heartbeat_timeout:
            logger.info(f"[DEBUG] 端口 {port} - 心跳超时")
        
        # 如果端口不活跃且进程不存在，或者心跳超时，标记为待清理
        if (not is_active and not is_process_alive) or (not is_active and heartbeat_timeout):
            logger.info(f"[DEBUG] 端口 {port} 已停止，将被清理")
            stopped_ports.append(port_str)
            continue  # 不添加到活跃列表
        
        # 更新状态：端口活跃且进程存活才是 running
        if is_active and is_process_alive:
            info['status'] = 'running'
        else:
            info['status'] = 'stopped'
        
        logger.info(f"[DEBUG] 端口 {port} - 端口活跃: {is_active}, 进程存活: {is_process_alive}, 状态: {info['status']}")
        active_instances[port_str] = info
    
    # 清理已停止的实例
    for port_str in stopped_ports:
        logger.info(f"[DEBUG] 从注册表中移除端口 {port_str}")
        del instances_registry[port_str]
    
    logger.info(f"[DEBUG] 返回 {len(active_instances)} 个活跃实例")
    return jsonify({'instances': active_instances})

@app.route('/hub/update-project-name', methods=['POST'])
def update_project_name():
    """更新实例的项目名称"""
    data = request.json
    port = str(data.get('port'))
    project_name = data.get('project_name', '')
    
    if port in instances_registry:
        instances_registry[port]['project_name'] = project_name
        logger.info(f"✅ 更新端口 {port} 的项目名称: {project_name}")
        return jsonify({'status': 'updated', 'port': port, 'project_name': project_name})
    
    return jsonify({'error': 'Instance not found'}), 404

@app.route('/hub/instance/<port>/status', methods=['GET'])
def get_instance_status(port):
    """获取单个实例的详细状态"""
    if port not in instances_registry:
        return jsonify({'error': 'Instance not found'}), 404
    
    info = instances_registry[port]
    
    # 如果是 app.py，尝试获取 workflow 状态
    if info['type'] == 'app':
        try:
            response = requests.get(
                f"http://127.0.0.1:{port}/workflow/status/current",
                timeout=2
            )
            if response.status_code == 200:
                workflow_data = response.json()
                info['workflow_status'] = workflow_data
        except Exception as e:
            logger.warning(f"无法获取 workflow 状态: {e}")
    
    # 如果是 workteam.py，获取消息统计
    if info['type'] == 'workteam':
        try:
            response = requests.get(
                f"http://127.0.0.1:{port}/get_state",
                timeout=2
            )
            if response.status_code == 200:
                state_data = response.json()
                # 统计消息：使用 msg['Received'] 区分已读/未读
                messages = state_data.get('messages', [])
                confirmed_count = 0
                for m in messages:
                    # Received 可能是 1/0、True/False、'1'/'0' 等
                    received = m.get('Received')
                    is_confirmed = False
                    if isinstance(received, bool):
                        is_confirmed = received
                    elif isinstance(received, (int, float)):
                        is_confirmed = (received == 1)
                    elif isinstance(received, str):
                        is_confirmed = received.strip() in ('1', 'true', 'True')
                    if is_confirmed:
                        confirmed_count += 1
                unconfirmed_count = len(messages) - confirmed_count
                info['message_stats'] = {
                    'total': len(messages),
                    'confirmed': confirmed_count,
                    'unconfirmed': unconfirmed_count
                }
                logger.info(f"[DEBUG] WorkTeam {port} 消息统计: total={len(messages)}, confirmed={confirmed_count}, unconfirmed={unconfirmed_count}")
        except Exception as e:
            logger.warning(f"无法获取 workteam 状态: {e}")

    return jsonify(info)

@app.route('/hub/instance/<port>/pause', methods=['POST'])
def pause_app_instance(port):
    """通过 Hub 暂停指定端口上的 app 工作流（避免前端跨域）"""
    if port not in instances_registry:
        return jsonify({'error': 'Instance not found'}), 404

    info = instances_registry[port]
    if info.get('type') != 'app':
        return jsonify({'error': 'Only app instances support pause/resume'}), 400

    data = request.json or {}
    workflow_id = data.get('workflow_id')

    base_url = f"http://127.0.0.1:{port}"

    try:
        # 如前端未提供 workflow_id，则先询问当前状态
        if not workflow_id:
            status_resp = requests.get(f"{base_url}/workflow/status/current", timeout=3)
            if status_resp.status_code == 200:
                status_data = status_resp.json()
                workflow_id = status_data.get('workflow_id')
                logger.info(f"[DEBUG] 从 /workflow/status/current 获取 workflow_id={workflow_id} (port={port})")

        if not workflow_id:
            return jsonify({'error': 'No active workflow to pause'}), 400

        resp = requests.post(f"{base_url}/workflow/pause/{workflow_id}", timeout=5)
        logger.info(f"[DEBUG] 向 app {port} 发送暂停请求，workflow_id={workflow_id}，状态码={resp.status_code}")
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        logger.error(f"❌ 暂停实例 {port} 的工作流失败: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/hub/instance/<port>/resume', methods=['POST'])
def resume_app_instance(port):
    """通过 Hub 恢复指定端口上的 app 工作流（避免前端跨域）"""
    if port not in instances_registry:
        return jsonify({'error': 'Instance not found'}), 404

    info = instances_registry[port]
    if info.get('type') != 'app':
        return jsonify({'error': 'Only app instances support pause/resume'}), 400

    data = request.json or {}
    workflow_id = data.get('workflow_id')

    base_url = f"http://127.0.0.1:{port}"

    try:
        # 如前端未提供 workflow_id，则先询问当前状态
        if not workflow_id:
            status_resp = requests.get(f"{base_url}/workflow/status/current", timeout=3)
            if status_resp.status_code == 200:
                status_data = status_resp.json()
                workflow_id = status_data.get('workflow_id')
                logger.info(f"[DEBUG] 从 /workflow/status/current 获取 workflow_id={workflow_id} (port={port})")

        if not workflow_id:
            return jsonify({'error': 'No paused workflow to resume'}), 400

        resp = requests.post(f"{base_url}/workflow/resume/{workflow_id}", timeout=5)
        logger.info(f"[DEBUG] 向 app {port} 发送恢复请求，workflow_id={workflow_id}，状态码={resp.status_code}")
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        logger.error(f"❌ 恢复实例 {port} 的工作流失败: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/hub/instance/<port>/stop', methods=['POST'])
def stop_instance(port):
    """停止实例（优雅关闭）"""
    if port not in instances_registry:
        return jsonify({'error': 'Instance not found'}), 404
    
    info = instances_registry[port]
    pid = info.get('pid')
    
    if not pid:
        # 如果没有 PID，直接从注册表删除
        logger.info(f"[DEBUG] 端口 {port} 没有 PID，直接移除")
        del instances_registry[port]
        return jsonify({'status': 'removed', 'port': port})
    
    try:
        process = psutil.Process(pid)
        if not process.is_running():
            # 进程已经不存在，直接从注册表删除
            logger.info(f"[DEBUG] 端口 {port} 进程已停止，移除注册")
            del instances_registry[port]
            return jsonify({'status': 'removed', 'port': port})
        
        # 进程存在，尝试终止
        process.terminate()
        process.wait(timeout=10)
        del instances_registry[port]
        logger.info(f"✅ 实例已停止并移除: port {port}")
        return jsonify({'status': 'stopped', 'port': port})
        
    except psutil.TimeoutExpired:
        # 超时，强制杀死
        try:
            process.kill()
            del instances_registry[port]
            logger.warning(f"⚠️ 强制停止实例: port {port}")
            return jsonify({'status': 'killed', 'port': port})
        except:
            pass
    except psutil.NoSuchProcess:
        # 进程不存在，直接删除注册
        logger.info(f"[DEBUG] 端口 {port} 进程不存在，移除注册")
        del instances_registry[port]
        return jsonify({'status': 'removed', 'port': port})
    except Exception as e:
        logger.error(f"❌ 停止实例失败: {e}")
        # 即使失败，也尝试从注册表移除
        if port in instances_registry:
            del instances_registry[port]
        return jsonify({'status': 'error', 'message': str(e), 'port': port})

@app.route('/hub/instance/<port>/stop-workflow', methods=['POST'])
def stop_workflow_instance(port):
    """只结束 app 内部的工作流，不关闭整个进程"""
    if port not in instances_registry:
        return jsonify({'error': 'Instance not found'}), 404

    info = instances_registry[port]
    if info.get('type') != 'app':
        return jsonify({'error': 'Only app instances support workflow stop'}), 400

    data = request.json or {}
    workflow_id = data.get('workflow_id')
    base_url = f"http://127.0.0.1:{port}"

    try:
        # 如前端未提供 workflow_id，则先询问当前状态
        if not workflow_id:
            status_resp = requests.get(f"{base_url}/workflow/status/current", timeout=3)
            if status_resp.status_code == 200:
                status_data = status_resp.json()
                workflow_id = status_data.get('workflow_id')
                logger.info(f"[DEBUG] 从 /workflow/status/current 获取 workflow_id={workflow_id} (port={port})")

        if not workflow_id:
            return jsonify({'error': 'No active workflow to stop'}), 400

        # 调用 app 内部的停止和清理接口
        stop_resp = requests.post(f"{base_url}/workflow/stop/{workflow_id}", timeout=5)
        logger.info(f"[DEBUG] 向 app {port} 发送 stop 请求，workflow_id={workflow_id}，状态码={stop_resp.status_code}")
        try:
            cleanup_resp = requests.post(f"{base_url}/workflow/cleanup/{workflow_id}", timeout=5)
            logger.info(f"[DEBUG] 向 app {port} 发送 cleanup 请求，workflow_id={workflow_id}，状态码={cleanup_resp.status_code}")
        except Exception as ce:
            logger.warning(f"清理工作流 {workflow_id} 失败（可忽略）: {ce}")

        return jsonify(stop_resp.json()), stop_resp.status_code
    except Exception as e:
        logger.error(f"❌ 结束实例 {port} 的工作流失败: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/hub/instance/<port>/run-workflow', methods=['POST'])
def run_workflow_instance(port):
    """
    通过 Hub 在指定的 app 实例上启动一次工作流。
    目标：等效于该实例前端 index.js 中点击一次 runButton 的“运行”效果。
    """
    if port not in instances_registry:
        return jsonify({'error': 'Instance not found'}), 404

    info = instances_registry[port]
    if info.get('type') != 'app':
        return jsonify({'error': 'Only app instances support workflow run'}), 400

    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1) 先向 app 查询当前 project_data（尽量使用已加载的工作流数据）
        try:
            proj_resp = requests.post(f"{base_url}/history-project", json={}, timeout=5)
            if proj_resp.status_code == 200:
                project_payload = proj_resp.json() or {}
            else:
                project_payload = {}
        except Exception as pe:
            logger.warning(f"[DEBUG] 无法从 app {port} 获取 history-project: {pe}")
            project_payload = {}

        # 如果拿不到任何图数据，很可能是该 App 尚未在前端加载项目
        # 这里仍然尝试启动，若 app 端报错则将错误透传给前端
        payload = {
            "graph_data": project_payload,
            "passivity_trigger_array": [],
            "array_trigger_array": []
        }

        resp = requests.post(
            f"{base_url}/workflow/start",
            json=payload,
            timeout=15
        )
        logger.info(f"[DEBUG] 向 app {port} 发送 run-workflow 请求，状态码={resp.status_code}")

        # 将 app 返回结果原样透传
        try:
            body = resp.json()
        except Exception:
            body = {"error": f"Non-JSON response from app on port {port}"}

        return jsonify(body), resp.status_code
    except Exception as e:
        logger.error(f"❌ 启动实例 {port} 的工作流失败: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/hub/instance/<port>/restart', methods=['POST'])
def restart_instance(port):
    """重启实例"""
    if port not in instances_registry:
        return jsonify({'error': 'Instance not found'}), 404
    
    info = instances_registry[port]
    instance_type = info['type']
    project_name = info['project_name']
    
    # 先停止
    stop_result = stop_instance(port)
    if isinstance(stop_result, tuple):
        return stop_result
    
    time.sleep(2)  # 等待端口释放
    
    # 重新启动
    if instance_type == 'app':
        return start_new_instance()
    elif instance_type == 'workteam':
        return start_new_workteam()
    
    return jsonify({'error': 'Unknown instance type'}), 400

@app.route('/hub/scan-ports', methods=['GET'])
def scan_ports():
    """扫描当前活跃的端口（app.py 和 workteam.py）"""
    found_instances = []
    
    # 扫描常见端口范围
    for port in range(3000, 5000):
        if is_port_in_use(port):
            # 尝试探测类型
            instance_type = detect_instance_type(port)
            if instance_type:
                found_instances.append({
                    'port': port,
                    'type': instance_type,
                    'registered': str(port) in instances_registry
                })
    
    return jsonify({'found': found_instances})

def detect_instance_type(port):
    """通过健康检查端点探测实例类型"""
    try:
        # 尝试 app.py 的特征端点
        response = requests.get(f"http://127.0.0.1:{port}/workflow/status/current", timeout=1)
        if response.status_code in [200, 404]:  # 404 也说明是 app.py
            return 'app'
    except:
        pass
    
    try:
        # 尝试 workteam.py 的特征端点
        response = requests.get(f"http://127.0.0.1:{port}/get_state", timeout=1)
        if response.status_code == 200:
            return 'workteam'
    except:
        pass
    
    return None

@socketio.on('connect')
def test_connect():
    emit('message', 'Connected to WebSocket')

# ==================== 密钥管理接口 ====================
@app.route('/api/secrets/get-llm-nodes', methods=['GET'])
def get_llm_nodes():
    """获取所有 NodeKind='LLm' 的节点名称"""
    try:
        nodes_dir = os.path.join(os.getcwd(), 'Nodes')
        if not os.path.exists(nodes_dir):
            return jsonify({'nodes': []})
        
        llm_nodes = []
        for filename in os.listdir(nodes_dir):
            if filename.endswith('.py'):
                file_path = os.path.join(nodes_dir, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if "NodeKind = 'LLm'" in content or 'NodeKind = "LLm"' in content:
                            node_name = filename[:-3]  # 去除 .py
                            llm_nodes.append(node_name)
                except Exception:
                    continue
        
        return jsonify({'nodes': llm_nodes})
    except Exception as e:
        logger.error(f"获取LLm节点失败: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/secrets/get-config', methods=['GET'])
def get_secrets_config():
    """获取密钥配置"""
    try:
        edit_dir = os.path.join(os.getcwd(), 'Edit')
        os.makedirs(edit_dir, exist_ok=True)
        config_path = os.path.join(edit_dir, 'Edit.json')
        
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                if 'secrets' not in config:
                    config['secrets'] = []
                if 'llmMappings' not in config:
                    config['llmMappings'] = {}
                return jsonify(config)
        else:
            return jsonify({'secrets': [], 'llmMappings': {}})
    except Exception as e:
        logger.error(f"获取密钥配置失败: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/secrets/save-config', methods=['POST'])
def save_secrets_config():
    """保存密钥配置，并将密钥值写入环境变量"""
    try:
        data = request.json
        edit_dir = os.path.join(os.getcwd(), 'Edit')
        os.makedirs(edit_dir, exist_ok=True)
        config_path = os.path.join(edit_dir, 'Edit.json')
        
        # 保存到文件
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # 将密钥值写入环境变量
        secrets = data.get('secrets', [])
        for secret in secrets:
            key_name = secret.get('name', '')
            key_value = secret.get('value', '')
            if key_name and key_value:
                os.environ[key_name] = key_value
                logger.info(f"✅ 已将密钥 '{key_name}' 写入环境变量")
        
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"保存密钥配置失败: {e}")
        return jsonify({'error': str(e)}), 500

def load_secrets_to_env():
    """启动时从 Edit/Edit.json 加载密钥到环境变量"""
    try:
        edit_dir = os.path.join(os.getcwd(), 'Edit')
        config_path = os.path.join(edit_dir, 'Edit.json')
        
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                secrets = config.get('secrets', [])
                for secret in secrets:
                    key_name = secret.get('name', '')
                    key_value = secret.get('value', '')
                    if key_name and key_value:
                        os.environ[key_name] = key_value
                        logger.info(f"✅ 启动时加载密钥 '{key_name}' 到环境变量")
    except Exception as e:
        logger.warning(f"启动时加载密钥失败: {e}")

if __name__ == '__main__':
    import sys

    # 启动时加载密钥到环境变量
    load_secrets_to_env()

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
