from flask import Flask, jsonify, render_template,request
import pandas as pd
import os
import hashlib
import json
import importlib.util
import sys
import subprocess
import textwrap
import ast
import traceback  # 确保已经导入traceback模块
import re
import traceback
import shutil
import importlib
import logging
import datetime
import time
import platform
from threading import Lock

app = Flask(__name__)
project_data = None  # 初始化为空
project_name = None  # 初始化为空
# 这是之前定义的函数，稍微修改以适应当前上下文
# 全局变量来存储后端状态
# 初始化后端状态
backend_state = {
    'version': 0,
    'agents': [],
    'messages': [],
    'limits': []
}
@app.route('/get_message_files', methods=['GET'])
def get_message_files():
    message_dir = 'TeamWork_Message'
    if not os.path.exists(message_dir):
        os.makedirs(message_dir)
    
    files = [f for f in os.listdir(message_dir) if f.endswith('.json')]
    return jsonify(files)
@app.route('/create_message_file', methods=['POST'])
def create_message_file():
    data = request.json
    filename = data.get('filename')
    
    if not filename.endswith('.json'):
        filename += '.json'
    
    file_path = os.path.join('TeamWork_Message', filename)
    
    try:
        # 创建空的 JSON 文件
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/load_message_file', methods=['POST'])
def load_message_file():
    try:
        data = request.json
        filename = data.get('filename')
        
        if not filename:
            return jsonify({'success': False, 'error': 'Filename is required'})
            
        file_path = os.path.join('TeamWork_Message', filename)
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'error': 'File not found'})
            
        with open(file_path, 'r', encoding='utf-8') as f:
            messages = json.load(f)
            
        # 使用字典语法更新 backend_state
        backend_state['messages'] = messages
            
        return jsonify({
            'success': True,
            'messages': messages
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})



@app.route('/save_message_file', methods=['POST'])
def save_message_file():
    data = request.json
    filename = data.get('filename')
    messages = data.get('messages')
    
    if not filename.endswith('.json'):
        filename += '.json'
    
    file_path = os.path.join('TeamWork_Message', filename)
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
@app.route('/refresh_state', methods=['POST'])
def refresh_state():
    global backend_state
    backend_state = {
        'agents': [],
        'messages': [],
        'limits': [],
        'version': 0  # 添加版本号，用于跟踪状态变化
    }
@app.route('/open_file', methods=['POST'])
def open_file():
    try:
        data = request.get_json()
        file_path = data.get('path')
        
        # 处理 '@TempFiles' 路径
        if '@TempFiles' in file_path:
            # 假设根目录下和当前目录下都有一个 TempFiles 文件夹
            root_temp_path = os.path.join(os.path.abspath(os.sep), 'TempFiles')
            current_temp_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'TempFiles')
            
            # 选择一个实际存在的路径
            if os.path.exists(root_temp_path):
                actual_path = root_temp_path
            elif os.path.exists(current_temp_path):
                actual_path = current_temp_path
            else:
                error_message = "'TempFiles' directory not found in expected locations."
                return jsonify({'success': False, 'error': error_message}), 404
            
            # 替换 '@TempFiles' 为实际路径
            file_path = file_path.replace('@TempFiles', actual_path)
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'error': '文件不存在'})
        
        # Windows系统
        if platform.system() == 'Windows':
            os.startfile(file_path)
        # macOS系统
        elif platform.system() == 'Darwin':
            subprocess.call(('open', file_path))
        # Linux系统
        else:
            subprocess.call(('xdg-open', file_path))
            
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/long_poll', methods=['POST'])
def long_poll():
    try:
        client_version = request.json.get('version', 0)
        
        wait_time = 30
        start_time = time.time()

        while time.time() - start_time < wait_time:
            # 在这里调用 update_messages_limit_status()
            update_messages_limit_status()

            if backend_state.get('version', 0) > client_version:
                print(f"[long_poll] return new version={backend_state.get('version', 0)} (> client={client_version})")
                return jsonify(backend_state)
            time.sleep(0.5)

        return '', 304
    except Exception as e:
        app.logger.error(f"Error in long_poll: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
def update_messages_limit_status():
    global backend_state
    updated_messages = backend_state.get('messages', [])
    version_updated = False  # 添加一个标志来检测版本是否需要更新
    
    #print("🔍 当前限制条件数量:", len(backend_state['limits']))
    #for idx, limit in enumerate(backend_state['limits'], 1):
        #print(f"🔸 限制 {idx}: from={limit.get('from', '无')}, to={limit.get('to', '无')}")
    
    for msg in updated_messages:
        #print(f"📨 检查消息: from={msg.get('from', '无')}, to={msg.get('to', '无')}, timestamp={msg.get('timestamp', '无')}, 当前IsLimit={msg.get('IsLimit', False)},当前Received={msg.get('Received',[])}")
        
        # 只有当 IsLimit 为 False 时才检查限制
        if not msg.get('IsLimit', False):
            for limit in backend_state['limits']:
                if (limit['from'] == msg['from'] and limit['to'] == msg['to']):
                    limit_times = limit.get('messages_Time', [])
                    if msg['timestamp'] not in limit_times:
                        msg['IsLimit'] = True
                        if 'messages_Time' not in limit:
                            limit['messages_Time'] = []
                        limit['messages_Time'].append(msg['timestamp'])
                        print(f"[update_messages_limit_status] set IsLimit=True for ts={msg['timestamp']} from={msg['from']} to={msg['to']}")
                        #print(f"🚨 触发限制: 消息 {msg['timestamp']} 被设置为IsLimit=True")
                        version_updated = True  # 如果有消息状态更新，设置标志

    backend_state['messages'] = updated_messages

    if version_updated:
        backend_state['version'] = backend_state.get('version', 0) + 1


@app.route('/update_state', methods=['POST'])
def update_state():
    global backend_state
    frontend_state = request.json

    if not frontend_state or not isinstance(frontend_state, dict):
        return jsonify({'status': 'error', 'message': 'Invalid state data'}), 400

    if not backend_state:
        backend_state = frontend_state
    else:
        backend_state['agents'] = frontend_state.get('agents', [])
        backend_state['limits'] = frontend_state.get('limits', [])
        
        new_messages = frontend_state.get('messages', [])
        updated_messages = []
        for new_msg in new_messages:
            existing_msg = next((msg for msg in backend_state['messages'] if msg['timestamp'] == new_msg['timestamp']), None)
            if existing_msg:
                merged_msg = existing_msg.copy()
                if new_msg.get('shouldUpdateFields'):
                    merged_msg['Received'] = new_msg['Received']
                    merged_msg['IsLimit'] = new_msg['IsLimit']
                    print(f"[update_state] shouldUpdateFields ts={merged_msg.get('timestamp')} Received->len={len(merged_msg['Received'])} IsLimit->{merged_msg['IsLimit']}")
                    #print(f"Updating message {merged_msg['timestamp']}: Received={merged_msg['Received']}, IsLimit={merged_msg['IsLimit']}")
                updated_messages.append(merged_msg)
            else:
                # 新消息注入
                if isinstance(new_msg, dict):
                    print(f"[update_state] new message ts={new_msg.get('timestamp')} from={new_msg.get('from')} to={new_msg.get('to')} IsLimit={new_msg.get('IsLimit')}")
                updated_messages.append(new_msg)

        backend_state['messages'] = updated_messages

    backend_state['version'] = backend_state.get('version', 0) + 1
    
    # 在更新状态后调用 update_messages_limit_status
    update_messages_limit_status()
    
    return jsonify(backend_state)

@app.route('/send_message', methods=['POST'])
def send_message():
    global backend_state
    try:
        data = request.json
        to = data.get('to')
        content = data.get('content')
        is_limite = data.get('is_limite', False)
        from_agent = data.get('From', 'Unknown')
        if not to or not content:
            return jsonify({'status': 'error', 'message': 'To and content are required'}), 400
        
        new_message = {
            'from': from_agent,
            'to': to,
            'content': content,
            'timestamp': datetime.datetime.utcnow().isoformat(),
            'Received': [],
            'IsLimit': is_limite,
            'type': 'sent'
        }
        
        backend_state['messages'].append(new_message)
        print(f"[send_message] ts={new_message['timestamp']} from={from_agent} to={to} limit={is_limite}")
        
        # 增加版本号
        backend_state['version'] = backend_state.get('version', 0) + 1
        
        return jsonify({
            'status': 'success',
            'message': 'Message sent successfully',
            'new_state': backend_state
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400
@app.route('/edit_message', methods=['POST'])
def edit_message():
    global backend_state
    message_data = request.json

    if not message_data or not isinstance(message_data, dict):
        return jsonify({'status': 'error', 'message': 'Invalid message data'}), 400

    timestamp = message_data.get('timestamp')
    if not timestamp:
        return jsonify({'status': 'error', 'message': 'Timestamp is required'}), 400

    # 在现有消息中查找具有相同时间戳的消息
    existing_msg = next((msg for msg in backend_state['messages'] if msg['timestamp'] == timestamp), None)
    if not existing_msg:
        return jsonify({'status': 'error', 'message': 'Message not found'}), 404

    # 更新消息内容
    existing_msg['from'] = message_data.get('from', existing_msg['from'])
    existing_msg['to'] = message_data.get('to', existing_msg['to'])
    existing_msg['content'] = message_data.get('content', existing_msg['content'])
    existing_msg['editedAt'] = message_data.get('editedAt', existing_msg.get('editedAt'))
    
    # 更新版本号
    backend_state['version'] = backend_state.get('version', 0) + 1

    return jsonify({'status': 'success', 'message': 'Message updated successfully', 'data': existing_msg})

@app.route('/get_messages', methods=['POST'])
def get_messages():
    global backend_state
    # 规范化代理名，避免前后空格或大小写差异导致匹配失败
    agent_name = (request.json.get('agent_name') or '').strip()
    if not agent_name:
        return jsonify({'status': 'error', 'message': 'Agent name is required'}), 400
    
    print(f"[get_messages] request agent_name={agent_name} total_msgs={len(backend_state.get('messages', []))}")
    response_messages = []
    history_messages = []
    state_changed = False
    
    # 找出所有与该agent有过交互的其他agent
    related_agents = set(['All'])
    for msg in backend_state['messages']:
        if msg['from'] == agent_name or msg['to'] == agent_name:
            related_agents.add(msg['from'])
            related_agents.add(msg['to'])
    
    for msg in backend_state['messages']:
        # 规范化消息字段，增强健壮性
        msg_from = str(msg.get('from', '')).strip()
        msg_to   = str(msg.get('to', '')).strip()
        # 检查是否为相关历史消息
        is_relevant = (msg_from == agent_name or msg_from in related_agents) and \
                      (msg_to == agent_name or msg_to in related_agents)
        
        if is_relevant:
            history_text = f"from:{msg_from},to:{msg_to},content:{msg.get('content','')}"
            history_messages.append(history_text)
        
        # 检查是否需要发送新消息
        should_send = (
            (
                msg_to == agent_name or
                (msg_to == "All" and msg_from != agent_name)
            ) and agent_name not in msg.get('Received', [])
        ) and (msg.get('IsLimit', False) == False)
        
        
        if should_send:
            print(f"[get_messages] -> will send ts={msg.get('timestamp')} from={msg_from} to={msg_to} receivedLen={len(msg.get('Received', []))} isLimit={msg.get('IsLimit', False)}")
            response_messages.append({
                "context": msg.get('content', ''),
                "From": msg_from,
                "History": '\n'.join(history_messages)
            })
            
            # 更新Received数组
            if 'Received' not in msg:
                msg['Received'] = []
            if agent_name not in msg['Received']:
                msg['Received'].append(agent_name)
                state_changed = True
    
    # 提升版本号以触发前端刷新：
    # 1) 若状态改变（例如新增 Received）
    # 2) 或者即便仅有返回消息但未修改状态，也主动通知一次
    if state_changed or len(response_messages) > 0:
        backend_state['version'] = backend_state.get('version', 0) + 1
    if len(response_messages) > 0:
        try:
            # 尽量打印简要信息，避免噪音
            sample = backend_state.get('messages', [])
            returned = [m for m in backend_state.get('messages', []) if (m.get('to') == agent_name or (m.get('to') == 'All' and m.get('from') != agent_name)) and agent_name not in m.get('Received', []) and (m.get('IsLimit', False) == False)]
            ts_list = [m.get('timestamp') for m in returned]
            print(f"[get_messages] response count={len(response_messages)} ts_list={ts_list}")
        except Exception as _:
            pass
    
    return jsonify(response_messages)


@app.route('/get_state', methods=['GET'])
def get_state():
    return jsonify(backend_state)

@app.route('/clear_state', methods=['POST'])
def clear_state():
    global backend_state
    backend_state = {'agents': [], 'messages': [], 'limits': []}
    return jsonify({'status': 'success', 'message': 'State cleared'})

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'})
def hash_file(filepath):
    """计算文件的SHA-256哈希值"""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()
def extract_node_kind(file_path):
    """从文件中提取NodeKind值"""
    node_kind_pattern = re.compile(r"NodeKind\s*=\s*'([^']+)'")
    try:
        with open(file_path, 'r', encoding='utf-8') as file:  # 指定使用utf-8编码读取
            contents = file.read()
    except UnicodeDecodeError:
        return 'EncodingError'  # 如果读取时发生编码错误，返回'EncodingError'
    
    match = node_kind_pattern.search(contents)
    if match:
        return match.group(1)
    else:
        return 'Unknown'  # 如果没有找到NodeKind，返回'Unknown'
def extract_node_function(file_path):
    """从文件中提取FunctionIntroduction值"""
    # 更新正则表达式以匹配包含换行符的单行字符串
    node_kind_pattern = re.compile(r"FunctionIntroduction\s*=\s*'([^']*)'")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as file:  # 指定使用utf-8编码读取
            contents = file.read()
    except UnicodeDecodeError:
        return 'EncodingError'  # 如果读取时发生编码错误，返回'EncodingError'
    
    match = node_kind_pattern.search(contents)
    if match:
        return match.group(1)  # 返回提取的字符串
    else:
        return 'Unknown'  # 如果没有找到FunctionIntroduction，返回'Unknown'
    
@app.route('/save', methods=['POST'])
def save_data():
    data = request.json
    content = data['data']
    file_name = data.get('fileName')
    
    # 确保文件名是有效的
    file_name = "".join(x for x in file_name if x.isalnum() or x in "._- ")
    filename = f'WorkTeam/{file_name}.json'

    try:
        os.makedirs('WorkTeam', exist_ok=True)
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(json.loads(content), f, ensure_ascii=False, indent=2)
        return jsonify({'message': f'Data saved successfully as {filename}'})
    except Exception as e:
        return jsonify({'message': f'Error saving data: {str(e)}'}), 500

@app.route('/')
def index():
    port = int(sys.argv[1])
    return render_template('workTeam.html', port=port)
@app.route('/export', methods=['POST'])
def export():
    data = request.json
    graph_data = data['graphData']
    file_name = data['fileName']
    Kind=data['type']
    if Kind=='full':
        full_function_code = generate_full_function(graph_data['nodes'], graph_data['edges'])
        full_function_code_modified = full_function_code.replace('false', 'False')

        export_path = 'Export'
        os.makedirs(export_path, exist_ok=True)
        file_path = os.path.join(export_path, f"{file_name}.py")

        # 写入初始文件
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(full_function_code_modified)

        # 读取文件，过滤空行，替换 '**n**' 为 '\\n'，并写回
        with open(file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            cleaned_lines = [line for line in lines if line.strip() != '']
            modified_lines = [line.replace('**n**', '\\n') for line in cleaned_lines]

        with open(file_path, 'w', encoding='utf-8') as file:
            file.writelines(modified_lines)

        return jsonify({'message': 'Graph data exported successfully, empty lines removed and replacements made'})
    elif Kind == 'independent':
        export_path = os.path.join('Export', 'Independ', file_name)
        os.makedirs(export_path, exist_ok=True)
        response = generate_independent_function(graph_data['nodes'], graph_data['edges'], export_path)

        return response
      
def generate_independent_function(nodes, edges, export_path):
    # 找到node文件夹中对应的nodes文件夹将他们复制粘贴到指定的Export\Independ文件夹中
    for node in nodes:
        script_name = node['name'] + '.py' if not node['name'].endswith('.py') else node['name']
        script_path = os.path.join('Nodes', script_name)
        if not os.path.exists(script_path):
            return jsonify({'error': f'Script {script_name} not found'}), 404

        destination_path = os.path.join(export_path, script_name)
        shutil.copy(script_path, destination_path)

    # 生成代码，并替换特定的文本
    tempcode = generate_independent_code(nodes, edges)
    modified_code = tempcode.replace('**n**', '\\n').replace('false', 'False').replace('true', 'True')
    modified_code = "\n".join([line for line in modified_code.splitlines() if line.strip() != ''])  # 过滤空行

    # 创建一个与文件夹同名的.py文件，并写入处理后的代码
    main_script_path = os.path.join(export_path, os.path.basename(export_path) + '.py')
    with open(main_script_path, 'w', encoding='utf-8') as file:
        file.write(modified_code)

    return jsonify({'message': 'Files successfully copied and main script created'})
def generate_independent_code(nodes, edges):
    #类似于generate_full_function函数，但是主代码是用于寻找节点文件夹中的py文件运行，其他一样
    unconnected_inputs, unconnected_outputs = get_unconnected_points(nodes, edges)
    input_params = [f"{info['target']}_{info['anchorIndex']}" for info in unconnected_inputs]
    input_params_str = ', '.join(input_params)

    # 初始化 Outputs 和 Inputs 的数量
    OutPutNum = len(unconnected_outputs)
    InPutNum = len(unconnected_inputs)
    InputDict = []
    for info in unconnected_inputs:
        for node in nodes:
            if node['id'] == info['target']:
                # 判断是处理输入还是输出
                if info['anchorIndex'] < len(node['Inputs']):
                    # 处理输入
                    input_item = node['Inputs'][info['anchorIndex']]
                    if 'Kind' in input_item:
                        #将input_item['Kind']存入InputDict字典中
                        InputDict.append(input_item['Kind'])
                break

    OutPutDict = []
    for info in unconnected_outputs:
        for node in nodes:
            if node['id'] == info['source']:
                total_inputs = len(node['Inputs'])
                # 判断是处理输入还是输出
                if info['anchorIndex'] >= total_inputs:
                    # 处理输出，调整索引以匹配输出列表
                    output_index = info['anchorIndex'] - total_inputs
                    if output_index < len(node['Outputs']):
                        output_item = node['Outputs'][output_index]
                        if 'Kind' in output_item:
                            OutPutDict.append(output_item['Kind'])
                break         
    # 根据未连接的输入和输出生成 Outputs 和 Inputs 的定义
    Outputs = [
    f"{{'Num': None, 'Kind': '{OutPutDict[index]}', 'Id': '{info['source']}_{info['anchorIndex']}', 'Context': None,'Boolean': False,'name': '{info['name']}','Link':0,'Description':'answer'}}"
    for index, info in enumerate(unconnected_outputs)
]
    Inputs = [
    f"{{'Num': {info['Num']}, 'Context': '{info['Context'] if info['Context'] != None else ''}', 'Boolean': {info['Boolean'] if info['Boolean'] != None else False}, 'Kind': '{InputDict[index]}', 'Id': 'Input{index + 1}', 'IsLabel': {info['IsLabel']}, 'name': '{info['name']}'}}"
    for index, info in enumerate(unconnected_inputs)
]
    nodes_json = json.dumps(nodes)
    edges_json = json.dumps(edges)
    unconnected_inputs_json = json.dumps(unconnected_inputs)
    unconnected_outputs_json = json.dumps(unconnected_outputs)
    unconnected_inputs_json =unconnected_inputs_json.replace('null', 'None')
    unconnected_outputs_json =unconnected_outputs_json.replace('null', 'None')
    unconnected_inputs_json =unconnected_inputs_json.replace('true', 'True')
    nodes_json =nodes_json.replace('null', 'None')
    edges_json =edges_json.replace('null', 'None')
    nodes_json =nodes_json.replace('true', 'True')
    edges_json =edges_json.replace('true', 'True')
    nodes_json =nodes_json.replace('false', 'False')
    edges_json =edges_json.replace('false', 'False')
    node_logic = []
    import_statements = set()  # 用于存储所有节点中的 import 语句
    all_functions = []
    for node in nodes:
        node_code = get_node_code(node)
        functions, new_code = extract_and_remove_functions(node_code)
        node_code = new_code
        if functions:
            all_functions.extend(functions)
        all_functions = list(set(all_functions))
        node_function_name = f"{node['id'].replace('.', '_')}_run_node"  # 替换点号为下划线
        # 移除额外的 return Outputs
        node_code_lines = node_code.splitlines()
        node_code_lines = [line for line in node_code_lines if line.strip()]  # 移除空行
        filtered_lines = []
        import_statements = set()  # 确保这是一个集合
        filtered_lines = []
        import_statements.add('import re')  # 使用add()方法添加'import re'语句from flask import Flask, request, jsonifyimport osimport sysimport traceback
        import_statements.add('import json')  # 使用add()方法添加'import json'语句
        import_statements.add('import hashlib')  # 使用add()方法添加'import hashlib'语句
        import_statements.add('from flask import Flask, jsonify, request')  # 使用add()方法添加'from flask import Flask, jsonify, request'语句
        import_statements.add('import os')
        import_statements.add('import sys')
        import_statements.add('import traceback')
        for line in node_code_lines:
            if line.startswith('import '):
                import_statements.add(line)
            else:
                filtered_lines.append(line)

        import_statements.add('import re')  # 使用add()方法添加'import re'语句
        node_code = '\n'.join(filtered_lines)
        node_code =node_code.replace('OutPutNum', 'OutPutNum_node')
        node_code =node_code.replace('InPutNum', 'InPutNum_node')
        # 替换所有"Outputs"和"Inputs"
        node_code = node_code.replace('Outputs', 'Outputs_node')
        node_code = node_code.replace('Inputs', 'Inputs_node')

        # 将方括号内的替换回原样
        node_code = node_code.replace("['Inputs_node']", "['Inputs']")
        node_code = node_code.replace("['Outputs_node']", "['Outputs']")

        node_code =node_code.replace('nodes', 'nodes_node')
        node_code =node_code.replace('edges', 'edges_node')
        node_code =node_code.replace('unconnected_inputs', 'unconnected_inputs_node')
        node_code =node_code.replace('unconnected_outputs', 'unconnected_outputs_node')
        node_code =node_code.replace('def run_node(node)', 'def run_nodes(node)')
        node_code +="\nreturn run_nodes(node)"
        node_logic.append(f"def {node_function_name}(node):\n{textwrap.indent(node_code, '   ')}\n ")
        optimized_code = '\n'.join(block.rstrip('\n') for block in node_logic) + '\n\n'
    unique_functions = list(set(all_functions))
    optimized_all_functions = '\n'.join(block.rstrip('\n') for block in all_functions) + '\n\n'
    execute_node_code = """
def run_node_route(node, node_name):
    data = request.json
    # 获取当前脚本的目录，而不是工作目录
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(current_script_dir, node_name)
    if not script_path.endswith('.py'):
        script_path += '.py'
    print('Script path:', script_path)  # Debug: Print the script path
    if not os.path.exists(script_path):
        return jsonify({'error': f'Script {node_name} not found'}), 404

    # 添加脚本目录到 sys.path 以便能够导入模块
    if os.path.dirname(script_path) not in sys.path:
        sys.path.append(os.path.dirname(script_path))
    try:
        module = __import__(os.path.splitext(node_name)[0])
        output = module.run_node(node)
        return jsonify({'output': output}), 200
    except Exception as e:
        error_info = traceback.format_exc()
        return jsonify({'error': str(e), 'trace': error_info}), 400
def execute_node(nodez):
    if nodez['firstRun'] and all(
        (not input['Isnecessary'] and not input.get('isConnected', False)) or nodez['inputStatus'][i]
        for i, input in enumerate(nodez['Inputs'])
    ):
        nodez['firstRun'] = False
        #检索同文件夹下的同名py文件，nodez['name']为文件名
        node_function_name = nodez['name']
        #检索同文件夹下的同名py文件，nodez['name']为文件名
        if not node_function_name.endswith('.py'):
            node_function_name += '.py'
        if not os.path.exists(node_function_name):
            response, status_code = run_node_route(nodez, node_function_name)  # 接收响应和状态码
            print('Response received with status:', status_code)  # Debug: Print the status code
            if status_code == 200:
                data = response.get_json()['output']
                print('Data received:', data)  # Debug: Print the data
                for i, output in enumerate(nodez['Outputs']):
                    if output['Kind'] == 'Num':
                        output['Num'] = data[i]['Num']
                    elif output['Kind'] == 'String':
                        output['Context'] = data[i]['Context']
                    elif output['Kind'] == 'Boolean':
                        output['Boolean'] = data[i]['Boolean']
                for i, uo in enumerate(unconnected_outputs):
                    source_id = uo["source"]
                    anchor_index = uo["anchorIndex"]
                    for node in nodes:
                        if node["id"] == source_id:
                            if len(node["Inputs"]) <= anchor_index < len(node["Inputs"]) + len(node["Outputs"]):
                                Outputs[i]= node["Outputs"][anchor_index-len(node["Inputs"])]  
                for io,edge in enumerate(edges): 
                    if edge['source'] == nodez['id']:
                        targetNode = next((n for n in nodes if n['id'] == edge['target']), None)
                        if targetNode and edge['targetAnchor'] == len(targetNode['Inputs']) + len(targetNode['Outputs']):
                            if data[edge['sourceAnchor'] - len(nodez['Inputs'])]['Boolean'] == True:
                                targetNode['IsTrigger'] = False
                        if (targetNode and len(targetNode['Inputs']) > edge['targetAnchor']) or (targetNode and len(targetNode['Inputs'])+len(targetNode['Outputs']) == edge['targetAnchor'] and targetNode['NodeKind'] == 'IfNode'):
                            if(targetNode and len(targetNode['Inputs']) > edge['targetAnchor']):
                                if(targetNode['Inputs'][edge['targetAnchor']]['Kind'] == 'Num'):
                                    targetNode['Inputs'][edge['targetAnchor']]['Num'] = data[edge['sourceAnchor'] - len(nodez['Inputs'])]['Num']
                                elif(targetNode['Inputs'][edge['targetAnchor']]['Kind'] == 'String'):
                                    targetNode['Inputs'][edge['targetAnchor']]['Context'] = data[edge['sourceAnchor'] - len(nodez['Inputs'])]['Context']
                                elif(targetNode['Inputs'][edge['targetAnchor']]['Kind'] == 'Boolean'):
                                    targetNode['Inputs'][edge['targetAnchor']]['Boolean'] = data[edge['sourceAnchor'] - len(nodez['Inputs'])]['Boolean']
                                print(f"Node {nodez['id']} output to Node {targetNode['id']}")
                                targetNode['inputStatus'][edge['targetAnchor']] = True
                            export_prompt = targetNode['prompt']
                            if targetNode['ExprotAfterPrompt'] == '':
                                temp = 'Please ensure the output is in JSON format**n**{**n**'
                                for index, output in enumerate(targetNode['ExprotAfterPrompt']):
                                    kind = ''
                                    if output['Kind'] == 'String':
                                        kind = 'String'
                                    elif output['Kind'] == 'Num':
                                        kind = 'Num'
                                    elif output['Kind'] == 'Boolean':
                                        kind = 'Boolean'
                                    temp += f'"{output["Id"]}": "{output["Description"]}" (you need output type:{kind})**n**'
                                temp += '}**n**'
                                targetNode['ExprotAfterPrompt'] = temp
                            matches = retrieve_content_within_braces(targetNode['prompt'])
                            for match in matches:
                                for input in targetNode['Inputs']:
                                    if input['name'] == match:
                                        if input['Kind'] == 'Num':
                                            export_prompt = export_prompt.replace(match, str(input['Num']))
                                        elif input['Kind'] == 'String':
                                            export_prompt = export_prompt.replace(match, input['Context'])
                                        elif input['Kind'] == 'Boolean':
                                            export_prompt = export_prompt.replace(match, str(input['Boolean']))
                                export_prompt = export_prompt.replace('{{', '').replace('}}', '')
                            print('prompt:', export_prompt)
                            targetNode['ExprotPrompt'] = export_prompt +'**n**' + targetNode.get('ExprotAfterPrompt', '')
                            print('ExprotPrompt:', targetNode['ExprotPrompt'])
                            if not targetNode.get('IsTrigger', False):
                                execute_node(targetNode)
            else:
                print(f"Error executing node: {response.get_json()['error']}")
        else:
            print(f"Function {node_function_name} not found")
"""

    return (
    '\n'.join(sorted(import_statements)) + '\n\n'
    + f"OutPutNum = {OutPutNum}\n"
    + f"InPutNum = {InPutNum}\n"
    + f"Outputs = [{', '.join(Outputs)}]\n"
    + f"Inputs = [{', '.join(Inputs)}]\n"
    + f"NodeKind = 'Normal'\n"
    + f"nodes = {nodes_json}\n"
    + f"edges = {edges_json}\n"
    + f"unconnected_inputs = {unconnected_inputs_json}\n"
    + f"unconnected_outputs = {unconnected_outputs_json}\n"
    + """
def run_node(nodex):
    for index, value in enumerate(nodex['Inputs']):
        if index < len(Inputs):
            if(Inputs[index]['Kind'] == 'Num'):
                Inputs[index]['Num'] = nodex['Inputs'][index]['Num']
            elif(Inputs[index]['Kind'] == 'String'):
                Inputs[index]['Context'] = nodex['Inputs'][index]['Context']
            elif(Inputs[index]['Kind'] == 'Boolean'):
                Inputs[index]['Boolean'] = nodex['Inputs'][index]['Boolean']
            print(f'Index {index} is updated with value {value}Num{Inputs[index]["Num"]}')
        else:
            print(f'Warning: input_args contains more items than Inputs. Extra value {value} at index {index} is ignored.')
    for i, Input in enumerate(Inputs):
        for node in nodes:
            if node['id']==unconnected_inputs[i]['target']:
                node['Inputs'][unconnected_inputs[i]["anchorIndex"]]['Num']=Input['Num']
                node['Inputs'][unconnected_inputs[i]["anchorIndex"]]['Context']=Input['Context']
                node['Inputs'][unconnected_inputs[i]["anchorIndex"]]['Boolean']=Input['Boolean']
    for node in nodes:
        node['inputStatus'] = [False] * len(node['Inputs'])
        node['firstRun'] = True
        node['IsTrigger'] = False
        if node['TriggerLink']>0:
            node['IsTrigger'] = True
        for output in node['Outputs']:
            output['Num'] = 0
            output['Context'] = ''
        for input in node['Inputs']:
            input['isConnected'] = False
    # 检查每个节点的每个输入矛点是否都被连接
    for node in nodes:
        for index, input in enumerate(node['Inputs']):
            isConnected = any(edge['target'] == node['id'] and edge['targetAnchor'] == index for edge in edges)
            if isConnected and not input['Isnecessary']:
                node['Inputs'][index]['isConnected'] = True
    for i, uo in enumerate(unconnected_inputs):
        target_id = uo['target']
        anchor_index = uo['anchorIndex']
        for node in nodes:
            if node['id'] == target_id:
                if 0 <= anchor_index < len(node['Inputs']):
                    node['inputStatus'][anchor_index] = True
    start_nodes = [node for node in nodes if len(node['Inputs']) == 0 or all(node['inputStatus'])]
    for node in start_nodes:
        if node['ExprotAfterPrompt'] == '':
            temp = 'Please ensure the output is in JSON format**n**{**n**'
            for index, output in enumerate(node['ExprotAfterPrompt']):
                kind = ''
                if output['Kind'] == 'String':
                    kind = 'String'
                elif output['Kind'] == 'Num':
                    kind = 'Num'
                elif output['Kind'] == 'Boolean':
                    kind = 'Boolean'
                temp += f'"{output["Id"]}": "{output["Description"]}" (you need output type:{kind})**n**'
            temp += '}**n**'
            node['ExprotAfterPrompt'] = temp     
        export_prompt = node['prompt']
        matches = retrieve_content_within_braces(node['prompt'])
        for match in matches:
            for input in node['Inputs']:
                if input['name'] == match:
                    if input['Kind'] == 'Num':
                        export_prompt = export_prompt.replace(match, str(input['Num']))
                    elif input['Kind'] == 'String':
                        export_prompt = export_prompt.replace(match, input['Context'])
                    elif input['Kind'] == 'Boolean':
                        export_prompt = export_prompt.replace(match, str(input['Boolean']))
            export_prompt = export_prompt.replace('{{', '').replace('}}', '')
        print('prompt:', export_prompt)
        node['ExprotPrompt'] = export_prompt + '**n**' + node.get('ExprotAfterPrompt', '')
        print('ExprotPrompt:', node['ExprotPrompt'])
        if not node.get('IsTrigger', False):
            execute_node(node)
    return Outputs
def retrieve_content_within_braces(text):
    return re.findall(r'{{(.*?)}}', text)
"""

    + execute_node_code+ '\n\n'
)
    
def conditional_replace(text, old, new):
    # 使用正则表达式定义替换规则，(?<!\[)' 和 '(?!\])' 确保 'old' 不在方括号内
    pattern = r'(?<!\[)' + re.escape(old) + r'(?!\])'
    replaced_text = re.sub(pattern, new, text)
    return replaced_text
def generate_full_function(nodes, edges):
    #for node in nodes:
      #  for i, input in enumerate(node['Inputs']):
        #    isConnected = any(edge['target'] == node['id'] and edge['targetAnchor'] == i for edge in edges)
        #    if not isConnected and input['Isnecessary']:
       #         raise Exception(f"节点 {node['name']} 的输入矛点 {input['Name']} 没有被连接")
            
    unconnected_inputs, unconnected_outputs = get_unconnected_points(nodes, edges)
    input_params = [f"{info['target']}_{info['anchorIndex']}" for info in unconnected_inputs]
    input_params_str = ', '.join(input_params)

    # 初始化 Outputs 和 Inputs 的数量
    OutPutNum = len(unconnected_outputs)
    InPutNum = len(unconnected_inputs)
    InputDict = []
    for info in unconnected_inputs:
        for node in nodes:
            if node['id'] == info['target']:
                # 判断是处理输入还是输出
                if info['anchorIndex'] < len(node['Inputs']):
                    # 处理输入
                    input_item = node['Inputs'][info['anchorIndex']]
                    if 'Kind' in input_item:
                        #将input_item['Kind']存入InputDict字典中
                        InputDict.append(input_item['Kind'])
                break

    OutPutDict = []
    for info in unconnected_outputs:
        for node in nodes:
            if node['id'] == info['source']:
                total_inputs = len(node['Inputs'])
                # 判断是处理输入还是输出
                if info['anchorIndex'] >= total_inputs:
                    # 处理输出，调整索引以匹配输出列表
                    output_index = info['anchorIndex'] - total_inputs
                    if output_index < len(node['Outputs']):
                        output_item = node['Outputs'][output_index]
                        if 'Kind' in output_item:
                            OutPutDict.append(output_item['Kind'])
                break         
    # 根据未连接的输入和输出生成 Outputs 和 Inputs 的定义
    Outputs = [
    f"{{'Num': None, 'Kind': '{OutPutDict[index]}', 'Id': '{info['source']}_{info['anchorIndex']}', 'Context': None,'Boolean': False,'name': '{info['name']}','Link':0,'Description':'answer'}}"
    for index, info in enumerate(unconnected_outputs)
]
    Inputs = [
    f"{{'Num': {info['Num']}, 'Context': '{info['Context'] if info['Context'] != None else ''}', 'Boolean': {info['Boolean'] if info['Boolean'] != None else False}, 'Kind': '{InputDict[index]}', 'Id': 'Input{index + 1}', 'IsLabel': {info['IsLabel']}, 'name': '{info['name']}'}}"
    for index, info in enumerate(unconnected_inputs)
]
    nodes_json = json.dumps(nodes)
    edges_json = json.dumps(edges)
    unconnected_inputs_json = json.dumps(unconnected_inputs)
    unconnected_outputs_json = json.dumps(unconnected_outputs)
    unconnected_inputs_json =unconnected_inputs_json.replace('null', 'None')
    unconnected_outputs_json =unconnected_outputs_json.replace('null', 'None')
    unconnected_inputs_json =unconnected_inputs_json.replace('true', 'True')
    nodes_json =nodes_json.replace('null', 'None')
    edges_json =edges_json.replace('null', 'None')
    nodes_json =nodes_json.replace('true', 'True')
    edges_json =edges_json.replace('true', 'True')
    nodes_json =nodes_json.replace('false', 'False')
    edges_json =edges_json.replace('false', 'False')
    node_logic = []
    import_statements = set()  # 用于存储所有节点中的 import 语句
    all_functions = []
    for node in nodes:
        node_code = get_node_code(node)
        functions, new_code = extract_and_remove_functions(node_code)
        node_code = new_code
        if functions:
            all_functions.extend(functions)
        all_functions = list(set(all_functions))
        node_function_name = f"{node['id'].replace('.', '_')}_run_node"  # 替换点号为下划线
        # 移除额外的 return Outputs
        node_code_lines = node_code.splitlines()
        node_code_lines = [line for line in node_code_lines if line.strip()]  # 移除空行
        filtered_lines = []
        import_statements = set()  # 确保这是一个集合
        filtered_lines = []

        for line in node_code_lines:
            if line.startswith('import '):
                import_statements.add(line)
            else:
                filtered_lines.append(line)

        import_statements.add('import re')  # 使用add()方法添加'import re'语句from flask import Flask, request, jsonifyimport osimport sysimport traceback
        import_statements.add('import json')  # 使用add()方法添加'import json'语句
        import_statements.add('import hashlib')  # 使用add()方法添加'import hashlib'语句
        import_statements.add('from flask import Flask, jsonify, request')  # 使用add()方法添加'from flask import Flask, jsonify, request'语句
        import_statements.add('import os')
        import_statements.add('import sys')
        import_statements.add('import traceback')  
        node_code = '\n'.join(filtered_lines)
        node_code =node_code.replace('OutPutNum', 'OutPutNum_node')
        node_code =node_code.replace('InPutNum', 'InPutNum_node')
        # 替换所有"Outputs"和"Inputs"
        node_code = node_code.replace('Outputs', 'Outputs_node')
        node_code = node_code.replace('Inputs', 'Inputs_node')

        # 将方括号内的替换回原样
        node_code = node_code.replace("['Inputs_node']", "['Inputs']")
        node_code = node_code.replace("['Outputs_node']", "['Outputs']")

        node_code =node_code.replace('nodes', 'nodes_node')
        node_code =node_code.replace('edges', 'edges_node')
        node_code =node_code.replace('unconnected_inputs', 'unconnected_inputs_node')
        node_code =node_code.replace('unconnected_outputs', 'unconnected_outputs_node')
        node_code =node_code.replace('def run_node(node)', 'def run_nodes(node)')
        node_code +="\nreturn run_nodes(node)"
        node_logic.append(f"def {node_function_name}(node):\n{textwrap.indent(node_code, '   ')}\n ")
        optimized_code = '\n'.join(block.rstrip('\n') for block in node_logic) + '\n\n'
    unique_functions = list(set(all_functions))
    optimized_all_functions = '\n'.join(block.rstrip('\n') for block in all_functions) + '\n\n'
    execute_node_code = """
def execute_node(nodez):
    if nodez['firstRun'] and all(
        (not input['Isnecessary'] and not input.get('isConnected', False)) or nodez['inputStatus'][i]
        for i, input in enumerate(nodez['Inputs'])
    ):
        nodez['firstRun'] = False
        node_function_name = f"{nodez['id'].replace('.', '_')}_run_node"
        node_function = globals().get(node_function_name)
        if node_function:
            data = node_function(nodez)
            for i, output in enumerate(nodez['Outputs']):
                if output['Kind'] == 'Num':
                 output['Num'] = data[i]['Num']
                elif output['Kind'] == 'String':
                    output['Context'] = data[i]['Context']
                elif output['Kind'] == 'Boolean':
                    output['Boolean'] = data[i]['Boolean']
            for i, uo in enumerate(unconnected_outputs):
                source_id = uo["source"]
                anchor_index = uo["anchorIndex"]
                for node in nodes:
                    if node["id"] == source_id:
                        if len(node["Inputs"]) <= anchor_index < len(node["Inputs"]) + len(node["Outputs"]):
                            Outputs[i]= node["Outputs"][anchor_index-len(node["Inputs"])]  
            for io,edge in enumerate(edges):
                if edge['source'] == nodez['id']:
                    targetNode = next((n for n in nodes if n['id'] == edge['target']), None)
                    if targetNode and edge['targetAnchor'] == len(targetNode['Inputs']) + len(targetNode['Outputs']):
                        if data[edge['sourceAnchor'] - len(nodez['Inputs'])]['Boolean'] == True:
                            targetNode['IsTrigger'] = False

                    if (targetNode and len(targetNode['Inputs']) > edge['targetAnchor']) or (targetNode and len(targetNode['Inputs'])+len(targetNode['Outputs']) == edge['targetAnchor'] and targetNode['NodeKind'] == 'IfNode'):
                        if(targetNode and len(targetNode['Inputs']) > edge['targetAnchor']):
                            if(targetNode['Inputs'][edge['targetAnchor']]['Kind'] == 'Num'):
                                targetNode['Inputs'][edge['targetAnchor']]['Num'] = data[edge['sourceAnchor'] - len(nodez['Inputs'])]['Num']
                            elif(targetNode['Inputs'][edge['targetAnchor']]['Kind'] == 'String'):
                                targetNode['Inputs'][edge['targetAnchor']]['Context'] = data[edge['sourceAnchor'] - len(nodez['Inputs'])]['Context']
                            elif(targetNode['Inputs'][edge['targetAnchor']]['Kind'] == 'Boolean'):
                                targetNode['Inputs'][edge['targetAnchor']]['Boolean'] = data[edge['sourceAnchor'] - len(nodez['Inputs'])]['Boolean']
                            print(f"Node {nodez['id']} output to Node {targetNode['id']}")
                            targetNode['inputStatus'][edge['targetAnchor']] = True
                        export_prompt = targetNode['prompt']
                        if targetNode['ExprotAfterPrompt'] == '':
                            temp = 'Please ensure the output is in JSON format**n**{**n**'
                            for index, output in enumerate(targetNode['ExprotAfterPrompt']):
                                kind = ''
                                if output['Kind'] == 'String':
                                    kind = 'String'
                                elif output['Kind'] == 'Num':
                                    kind = 'Num'
                                elif output['Kind'] == 'Boolean':
                                    kind = 'Boolean'
                                temp += f'"{output["Id"]}": "{output["Description"]}" (you need output type:{kind})**n**'
                            temp += '}**n**'
                            targetNode['ExprotAfterPrompt'] = temp
                        matches = retrieve_content_within_braces(targetNode['prompt'])
                        for match in matches:
                            for input in targetNode['Inputs']:
                                if input['name'] == match:
                                    if input['Kind'] == 'Num':
                                        export_prompt = export_prompt.replace(match, str(input['Num']))
                                    elif input['Kind'] == 'String':
                                        export_prompt = export_prompt.replace(match, input['Context'])
                                    elif input['Kind'] == 'Boolean':
                                        export_prompt = export_prompt.replace(match, str(input['Boolean']))
                            export_prompt = export_prompt.replace('{{', '').replace('}}', '')
                        print('prompt:', export_prompt)
                        targetNode['ExprotPrompt'] = export_prompt +'**n**' + targetNode.get('ExprotAfterPrompt', '')
                        print('ExprotPrompt:', targetNode['ExprotPrompt'])
                        if not targetNode.get('IsTrigger', False):
                            execute_node(targetNode)
        else:
            print(f"Function {node_function_name} not found")
"""

    return (
    '\n'.join(sorted(import_statements)) + '\n\n'
    + f"OutPutNum = {OutPutNum}\n"
    + f"InPutNum = {InPutNum}\n"
    + f"Outputs = [{', '.join(Outputs)}]\n"
    + f"Inputs = [{', '.join(Inputs)}]\n"
    + f"NodeKind = 'Normal'\n"
    + f"nodes = {nodes_json}\n"
    + f"edges = {edges_json}\n"
    + f"unconnected_inputs = {unconnected_inputs_json}\n"
    + f"unconnected_outputs = {unconnected_outputs_json}\n"
    + """
def run_node(nodex):
    for index, value in enumerate(nodex['Inputs']):
        if index < len(Inputs):
            if(Inputs[index]['Kind'] == 'Num'):
                Inputs[index]['Num'] = nodex['Inputs'][index]['Num']
            elif(Inputs[index]['Kind'] == 'String'):
                Inputs[index]['Context'] = nodex['Inputs'][index]['Context']
            elif(Inputs[index]['Kind'] == 'Boolean'):
                Inputs[index]['Boolean'] = nodex['Inputs'][index]['Boolean']
            print(f'Index {index} is updated with value {value}Num{Inputs[index]["Num"]}')
        else:
            print(f'Warning: input_args contains more items than Inputs. Extra value {value} at index {index} is ignored.')
    for i, Input in enumerate(Inputs):
        for node in nodes:
            if node['id']==unconnected_inputs[i]['target']:
                node['Inputs'][unconnected_inputs[i]["anchorIndex"]]['Num']=Input['Num']
                node['Inputs'][unconnected_inputs[i]["anchorIndex"]]['Context']=Input['Context']
                node['Inputs'][unconnected_inputs[i]["anchorIndex"]]['Boolean']=Input['Boolean']
    for node in nodes:
        node['inputStatus'] = [False] * len(node['Inputs'])
        node['firstRun'] = True
        node['IsTrigger'] = False
        if node['TriggerLink']>0:
            node['IsTrigger'] = True
        for output in node['Outputs']:
            output['Num'] = 0
            output['Context'] = ''
        for input in node['Inputs']:
            input['isConnected'] = False
    # 检查每个节点的每个输入矛点是否都被连接
    for node in nodes:
        for index, input in enumerate(node['Inputs']):
            isConnected = any(edge['target'] == node['id'] and edge['targetAnchor'] == index for edge in edges)
            if isConnected and not input['Isnecessary']:
                node['Inputs'][index]['isConnected'] = True
    for i, uo in enumerate(unconnected_inputs):
        target_id = uo['target']
        anchor_index = uo['anchorIndex']
        for node in nodes:
            if node['id'] == target_id:
                if 0 <= anchor_index < len(node['Inputs']):
                    node['inputStatus'][anchor_index] = True
    start_nodes = [node for node in nodes if len(node['Inputs']) == 0 or all(node['inputStatus'])]
    for node in start_nodes:
        if node['ExprotAfterPrompt'] == '':
            temp = 'Please ensure the output is in JSON format**n**{**n**'
            for index, output in enumerate(node['ExprotAfterPrompt']):
                kind = ''
                if output['Kind'] == 'String':
                    kind = 'String'
                elif output['Kind'] == 'Num':
                    kind = 'Num'
                elif output['Kind'] == 'Boolean':
                    kind = 'Boolean'
                temp += f'"{output["Id"]}": "{output["Description"]}" (you need output type:{kind})**n**'
            temp += '}**n**'
            node['ExprotAfterPrompt'] = temp     
        export_prompt = node['prompt']
        matches = retrieve_content_within_braces(node['prompt'])
        for match in matches:
            for input in node['Inputs']:
                if input['name'] == match:
                    if input['Kind'] == 'Num':
                        export_prompt = export_prompt.replace(match, str(input['Num']))
                    elif input['Kind'] == 'String':
                        export_prompt = export_prompt.replace(match, input['Context'])
                    elif input['Kind'] == 'Boolean':
                        export_prompt = export_prompt.replace(match, str(input['Boolean']))
            export_prompt = export_prompt.replace('{{', '').replace('}}', '')
        print('prompt:', export_prompt)
        node['ExprotPrompt'] = export_prompt + '**n**' + node.get('ExprotAfterPrompt', '')
        print('ExprotPrompt:', node['ExprotPrompt'])
        if not node.get('IsTrigger', False):
            execute_node(node)
    return Outputs
def retrieve_content_within_braces(text):
    return re.findall(r'{{(.*?)}}', text)
"""

    + execute_node_code+ '\n\n'
    + optimized_code
    + optimized_all_functions
)
    
def extract_and_remove_functions(code):
    # 如果存在，则从 "print(f"Function {node_function_name} not found")" 之后开始提取内容
    if "print(f\"Function {node_function_name} not found\")" in code:
        start_index = code.index("print(f\"Function {node_function_name} not found\")") + len("print(f\"Function {node_function_name} not found\")")
    elif "return Outputs_node" in code:
        # 如果不存在，则从 "return Outputs_node" 之后开始提取内容
        start_index = code.index("return Outputs_node") + len("return Outputs_node")
    else:
        # 如果都不存在，可以选择一个合适的默认行为
        start_index = len(code)  # 例如，可以设置为代码的末尾

    functions_part = code[start_index:]

    # 提取整个函数定义，包括函数名、参数和函数体
    function_defs = re.findall(r"def\s.*?return run_nodes\(input_argss\)", functions_part, re.DOTALL)

    # 将每个函数定义分开并放入数组
    function_defs = [f.strip() for f in function_defs]

    # 从原始代码中删除这些函数定义
    for func_def in function_defs:
        code = code.replace(func_def, '')

    return function_defs, code

def get_unconnected_points(nodes, edges):
    # 创建一个用于存储所有节点的锚点信息的列表
    anchors = []
    for node in nodes:
        index=-1
        for i, input in enumerate(node['Inputs']):
            Temp=False
            if(input['IsLabel']==True):
                Temp=True
            print('测试',input)
            # 假设 info 是之前定义好的字典
            info = {'Boolean': None, 'Context': None}  # 你可能需要根据实际情况来初始化这个字典
            # 检查并设置默认值
            if info['Boolean'] is None:
                info['Boolean'] = False
            if info['Context'] is None:
                info['Context'] = ''
            anchors.append({
                'NodeId': node['id'], 
                'IsOutputOrInput': 'Input', 
                'anchorIndex': i, 
                'IsConnected': False,
                'name': input['name'],
                'IsLabel': Temp,
                'Kind': input['Kind'],
                'Num': input['Num'],
                'Context': info['Context'],  # 使用更新后的info字典中的值
                'Boolean': info['Boolean']  # 同上
            })
            index=i
        for i, output in enumerate(node['Outputs']):
            anchors.append({'NodeId': node['id'], 'IsOutputOrInput': 'Output', 'anchorIndex': i+index+1, 'IsConnected': False,'name':output['name']})
    
    # 遍历边，更新连接的锚点信息
    for edge in edges:
        # 更新输入锚点的连接状态
        for anchor in anchors:
            if anchor['NodeId'] == edge['target'] and anchor['anchorIndex'] == edge['targetAnchor'] and anchor['IsOutputOrInput'] == 'Input':
                anchor['IsConnected'] = True
                anchor['source'] = edge['source']
                anchor['sourceAnchor'] = edge['sourceAnchor']
        # 更新输出锚点的连接状态
        for anchor in anchors:
            if anchor['NodeId'] == edge['source'] and anchor['anchorIndex'] == edge['sourceAnchor'] and anchor['IsOutputOrInput'] == 'Output':
                anchor['IsConnected'] = True
                anchor['target'] = edge['target']
                anchor['targetAnchor'] = edge['targetAnchor']
    
    # 根据连接状态将锚点分配到未连接的输入和输出列表中
    unconnected_inputs = [
        {'source': anchor.get('source'), 'sourceAnchor': anchor.get('sourceAnchor'), 'target': anchor['NodeId'], 'anchorIndex': anchor['anchorIndex'],'name':anchor['name'],'IsLabel':anchor['IsLabel'],'Kind':anchor['Kind'],'Num':anchor['Num'],'Context':anchor['Context'],'Boolean':anchor['Boolean']}
        for anchor in anchors if anchor['IsOutputOrInput'] == 'Input' and not anchor['IsConnected']
    ]
    unconnected_outputs = [
        {'source': anchor['NodeId'], 'anchorIndex': anchor['anchorIndex'], 'target': anchor.get('target'), 'targetAnchor': anchor.get('targetAnchor'),'name':anchor['name']}
        for anchor in anchors if anchor['IsOutputOrInput'] == 'Output' and not anchor['IsConnected']
    ]

    return unconnected_inputs, unconnected_outputs

def extract_and_remove_run_node_code(script_content):
    # 正则表达式匹配 return Outputs 后面的所有内容
    pattern = re.compile(r'(return Outputs[\s\S]*?(?=return run_nodes\())', re.MULTILINE)
    matches = pattern.findall(script_content)

    # 如果找到了匹配的内容，则提取代码并存储到数组中，并从原始脚本中移除该部分的代码
    if matches:
        run_node_code = matches[0].strip().split('\n')
        modified_script_content = pattern.sub('', script_content).strip()
        return modified_script_content, run_node_code
    else:
        return script_content, []

def get_node_code(node):
    script_name = node['name'] if node['name'].endswith('.py') else f"{node['name']}.py"
    script_path = os.path.join('Nodes', script_name)
    try:
        with open(script_path, 'rb') as file:
            content = file.read()
            decoded_content = content.decode('utf-8', errors='ignore')
            cleaned_content = decoded_content.replace('Ƹ', '').replace('�', '')
            return cleaned_content
    except FileNotFoundError:
        print(f"File not found: {script_path}")
        return ""
    except Exception as e:
        print(f"Error reading file {script_path}: {e}")
        return ""
lock = Lock()
@app.route('/run-node', methods=['POST'])
def run_node_route():
    data = request.json
    node_name = data.get('name')
    node = data.get('node', {})
    script_path = os.path.join('Nodes', node_name)
    if not script_path.endswith('.py'):
        script_path += '.py'

    if not os.path.exists(script_path):
        return jsonify({'error': f'Script {node_name} not found'}), 404

    try:
        # 加锁，防止并发时的模块冲突
        with lock:
            # 将模块所在目录加入sys.path
            module_dir = os.path.dirname(script_path)
            if module_dir not in sys.path:
                sys.path.insert(0, module_dir)

            # 获取模块名（不带扩展名）
            module_name = os.path.splitext(os.path.basename(node_name))[0]

            # 从 sys.modules 中移除模块，强制重新加载
            if module_name in sys.modules:
                del sys.modules[module_name]

            module = importlib.import_module(module_name)
            
        # 执行模块的函数
        output = module.run_node(node)
        return jsonify({'output': output})
    except Exception as e:
        error_info = traceback.format_exc()
        return jsonify({'error': str(e), 'trace': error_info}), 400

# Function to generate Excel column label (A, B, C, ..., AA, AB, ...)
def get_excel_column_label(index):
    label = ''
    while index >= 0:
        label = chr(index % 26 + ord('A')) + label
        index = index // 26 - 1
    return label

# Reading Excel data and JSON data, and returning by Sheet and row
@app.route('/read_DataBase', methods=['POST'])
def read_data():
    try:
        # 获取文件路径
        data = request.get_json() or {}
        if 'file_path' not in data:
            return jsonify({'status': 'fail', 'message': 'No file path provided in the request'})

        file_path = data['file_path']
        include_rows = int(data.get('include_rows', 0) or 0)  # 0 = 仅返回表名/列名；>0 = 每个表/Sheet 额外返回前 N 行预览
        max_json_records = int(data.get('max_json_records', 5000) or 5000)
        schema_only = include_rows <= 0

        # 检查文件是否存在
        if not os.path.exists(file_path):
            return jsonify({'status': 'fail', 'message': 'File not found'})

        response_data = {}
        columns_data = {}
        file_ext = os.path.splitext(file_path)[1].lower()

        # 根据文件类型进行处理（默认只读“表名/列名”，避免不科学的全量读表）
        if file_ext in ['.xlsx', '.xls']:
            try:
                excel_data = pd.ExcelFile(file_path)
                for sheet_name in excel_data.sheet_names:
                    df_head = excel_data.parse(sheet_name, nrows=0)
                    formatted_cols = [
                        f"{i+1}/{get_excel_column_label(i)}/{col if 'Unnamed' not in str(col) else 'Unnamed'}"
                        for i, col in enumerate(df_head.columns)
                    ]
                    columns_data[sheet_name] = formatted_cols
                    if not schema_only:
                        df = excel_data.parse(sheet_name, nrows=include_rows)
                        df.columns = formatted_cols
                        df = df.fillna("Empty")
                        response_data[sheet_name] = df.to_dict(orient='records')
            except Exception as e:
                return jsonify({'status': 'fail', 'message': f'Error processing Excel file: {str(e)}'})

        elif file_ext in ['.json', '.jsonl']:
            try:
                sheet_name = 'default'
                all_columns = set()
                json_data = []

                if file_ext == '.jsonl':
                    limit = include_rows if not schema_only else max_json_records
                    with open(file_path, 'r', encoding='utf-8') as jsonl_file:
                        for line in jsonl_file:
                            if limit <= 0:
                                break
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                obj = json.loads(line)
                            except json.JSONDecodeError as line_error:
                                logging.warning(f'Skipping invalid JSON line: {line}, Error: {str(line_error)}')
                                continue
                            if isinstance(obj, dict):
                                all_columns.update(obj.keys())
                            if not schema_only:
                                json_data.append(obj)
                            limit -= 1
                else:
                    streamed = False
                    if schema_only:
                        try:
                            import ijson  # type: ignore
                            with open(file_path, 'rb') as f:
                                seen_any = False
                                count = 0
                                for obj in ijson.items(f, 'item'):
                                    seen_any = True
                                    if isinstance(obj, dict):
                                        all_columns.update(obj.keys())
                                    count += 1
                                    if count >= max_json_records:
                                        break
                            streamed = seen_any
                        except Exception:
                            streamed = False

                    if not streamed:
                        with open(file_path, 'r', encoding='utf-8') as json_file:
                            data_content = json.load(json_file)
                        if isinstance(data_content, list):
                            iterable = data_content[:include_rows] if not schema_only else data_content[:max_json_records]
                        else:
                            iterable = [data_content]
                        for item in iterable:
                            if isinstance(item, dict):
                                all_columns.update(item.keys())
                            if not schema_only:
                                json_data.append(item)

                columns_data[sheet_name] = sorted(list(all_columns))
                if not schema_only:
                    response_data[sheet_name] = json_data
            except json.JSONDecodeError as json_error:
                return jsonify({'status': 'fail', 'message': f'Invalid JSON format: {str(json_error)}'})
            except Exception as e:
                return jsonify({'status': 'fail', 'message': f'Error reading JSON/JSONL file: {str(e)}'})

        elif file_ext in ['.db', '.sqlite']:
            try:
                import sqlite3
                from pathlib import Path

                conn = None
                try:
                    p = Path(file_path).resolve()
                    db_uri = f"file:{p.as_posix()}?mode=ro"
                    conn = sqlite3.connect(db_uri, uri=True, timeout=5.0)
                except Exception:
                    conn = sqlite3.connect(file_path, timeout=5.0)

                cur = conn.cursor()
                cur.execute("PRAGMA query_only=ON;")
                cur.execute("PRAGMA busy_timeout=5000;")

                def _quote_ident(name: str) -> str:
                    return '"' + str(name).replace('"', '""') + '"'

                table_rows = cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
                table_names = [r[0] for r in table_rows]

                for table_name in table_names:
                    try:
                        pragma_sql = f"PRAGMA table_info({_quote_ident(table_name)})"
                        info_rows = cur.execute(pragma_sql).fetchall()
                        columns_data[table_name] = [r[1] for r in info_rows]

                        if not schema_only:
                            q = f"SELECT * FROM {_quote_ident(table_name)} LIMIT ?"
                            cur2 = conn.cursor()
                            cur2.execute(q, (include_rows,))
                            col_names = [d[0] for d in cur2.description] if cur2.description else []
                            rows = cur2.fetchall()
                            response_data[table_name] = [
                                {col_names[i]: ("Empty" if v is None else v) for i, v in enumerate(row)}
                                for row in rows
                            ]
                    except Exception as table_e:
                        if not schema_only:
                            response_data[table_name] = []
                        columns_data[table_name] = []
                        logging.warning(f"SQLite table schema/read failed: {table_name}: {table_e}")

                conn.close()
            except Exception as e:
                try:
                    if conn is not None:
                        conn.close()
                except Exception:
                    pass
                return jsonify({'status': 'fail', 'message': f'Error processing SQLite file: {str(e)}'})

        else:
            return jsonify({'status': 'fail', 'message': 'Invalid file type. Only .xlsx, .json, .jsonl, .db and .sqlite are allowed.'})

        return jsonify({
            'status': 'success',
            'resolved_path': file_path,
            'tables': list(columns_data.keys()),
            'columns': columns_data,
            'data': response_data,
        })

    except Exception as e:
        return jsonify({'status': 'fail', 'message': str(e)})
@app.route('/open-code-editor', methods=['POST'])
def open_code_editor():
    data = request.json
    node_name = data.get('name')
    script_path = os.path.join('Nodes', node_name)
    if not script_path.endswith('.py'):
        script_path += '.py'

    if not os.path.exists(script_path):
        return jsonify({'error': f'Script {node_name} not found'}), 404

    try:
        os.system(f'code {script_path}')
        return jsonify({'status': 'success'})
    except Exception as e:
        error_info = traceback.format_exc()
        return jsonify({'error': str(e), 'trace': error_info}), 400
@app.route('/get-python-files')
def get_python_files():
    folder_path = 'Nodes'
    """在程序启动时运行，为Nodes文件夹中的每个Python文件生成哈希值，并以特定格式存入JSON文件中"""
    file_hashes = []  # 使用列表来存储字典
    for file in os.listdir(folder_path):
        if file.endswith(".py"):
            file_path = os.path.join(folder_path, file)
            hash_value = hash_file(file_path)  # 获取哈希值
            node_kind = extract_node_kind(file_path)
            node_function = extract_node_function(file_path)
            file_hashes.append({"Filename": file, "Hash": hash_value,"NodeKind": node_kind,"NodeFunction":node_function})
            
    
    json_path = os.path.join(folder_path, "jsonlist.json")
    with open(json_path, 'w') as json_file:
        json.dump(file_hashes, json_file, indent=4)
    # 读取json文件，获取存储的文件信息
    json_path = os.path.join('Nodes', 'jsonlist.json')
    with open(json_path, 'r') as json_file:
        file_hashes = json.load(json_file)
    
    # 创建一个包含多个字典的列表，每个字典包含文件名和对应的哈希值
    files_info = [{'filename': file_hash['Filename'], 'hash': file_hash['Hash'],'NodeKind':file_hash['NodeKind'],'NodeFunction':file_hash['NodeFunction']} for file_hash in file_hashes]

    # 将列表转换为 JSON 格式并返回
    return jsonify(files_info)


def find_imports(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    # 更新正则表达式以捕获import和from ... import ...语句
    imports = re.findall(r'^\s*(?:import\s+([^\s,]+)|from\s+([^\s,]+)\s+import)', content, re.MULTILINE)
    # 提取所有导入的模块名称
    imports = [imp[0] or imp[1] for imp in imports]
    return imports

def is_installed(package):
    try:
        __import__(package)
        return True
    except ImportError:
        return False
@app.route('/get-project-files', methods=['POST'])
def get_project_files():
    
    data = request.get_json()
    json_name = data['json_name']
    file_path = os.path.join(data['json_path'], json_name)
    
    if not os.path.isfile(file_path):
        return jsonify({'error': 'File not found'}), 404
    
    with open(file_path, 'r', encoding='utf-8') as file:
        file_data = json.load(file)
    
    return jsonify(file_data)
@app.route('/browse', methods=['POST'])
def browse_directory():
    dir_path = request.json.get('path', '.')  # 获取请求中的路径，如果没有提供则默认为当前目录
    
    # 检查路径是否包含文件后缀
    if os.path.splitext(dir_path)[1]:  # 如果路径包含文件后缀
        dir_path = os.path.dirname(dir_path)  # 退回到文件所在的文件夹
    
    # 检查路径安全性
    if not os.path.isabs(dir_path):
        dir_path = os.path.abspath(os.path.join('.', dir_path))
    
    try:
        items = []
        for item in os.listdir(dir_path):  # 遍历目录中的所有项目
            item_path = os.path.join(dir_path, item)
            items.append({
                'name': item,
                'is_dir': os.path.isdir(item_path),  # 判断是否是文件夹
                'path': item_path
            })
        
        logging.info(f"Successfully browsed directory: {dir_path}")
        return jsonify(items)
    
    except FileNotFoundError:
        error_message = f"Directory not found: {dir_path}"
        logging.error(error_message)
        return jsonify({'error': error_message}), 404
    
    except PermissionError:
        error_message = f"Permission denied for directory: {dir_path}"
        logging.error(error_message)
        return jsonify({'error': error_message}), 403
    
    except Exception as e:
        error_message = f"An error occurred while browsing directory: {dir_path} - {str(e)}"
        logging.error(error_message)
        return jsonify({'error': error_message}), 500

@app.route('/addHistory', methods=['POST'])
def add_history():
    data = request.json
    project_name = request.args.get('ProjectName')

    # 兼容前端开关：RecordHistory=0 时不落盘
    try:
        rh = request.args.get('RecordHistory')
        if rh is not None and str(rh).strip().lower() in ('0', 'false', 'no', 'off', 'disabled', 'disable'):
            return jsonify({'message': 'History recording disabled'}), 200
    except Exception:
        pass
    
    if not project_name:
        return jsonify({'error': 'ProjectName is required'}), 400

    history_dir = 'History'
    if not os.path.exists(history_dir):
        os.makedirs(history_dir)
    
    file_path = os.path.join(history_dir, f'{project_name}.json')

    # 如果文件存在，读取文件内容，否则创建一个空数组
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
    else:
        json_data = []

    # 保护：截断超长字符串，避免单条记录撑爆文件
    def _trunc(obj, max_chars: int = 20000, _depth: int = 0):
        if _depth > 6:
            return obj
        try:
            if isinstance(obj, str):
                if max_chars and len(obj) > max_chars:
                    return obj[:max_chars] + f"\n...[truncated {len(obj) - max_chars} chars]"
                return obj
            if isinstance(obj, list):
                return [_trunc(x, max_chars=max_chars, _depth=_depth + 1) for x in obj]
            if isinstance(obj, dict):
                return {k: _trunc(v, max_chars=max_chars, _depth=_depth + 1) for k, v in obj.items()}
        except Exception:
            return obj
        return obj
    if isinstance(data, dict):
        data = _trunc(data)

    # 将数据添加到现有的最后一个数组中（并做裁剪）
    if not json_data or not isinstance(json_data[-1], list):
        json_data.append([])
    json_data[-1].append(data)
    try:
        if isinstance(json_data[-1], list) and len(json_data[-1]) > 500:
            json_data[-1] = json_data[-1][-500:]
    except Exception:
        pass
    try:
        if isinstance(json_data, list) and len(json_data) > 30:
            json_data = json_data[-30:]
    except Exception:
        pass

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, separators=(',', ':'))

    return jsonify({'message': 'Data added successfully'}), 200
def is_process_running(script_name):
    """检查指定的脚本是否正在运行"""
    try:
        result = subprocess.run(['pgrep', '-fl', script_name], capture_output=True, text=True)
        return script_name in result.stdout
    except Exception as e:
        print(f"Error checking process: {e}")
        return False

@app.route('/start_Message', methods=['POST'])
def start_message():
    data = request.get_json()
    project_name = data.get('ProjectName')
    # 检查Message.py是否正在运行
    if not is_process_running('Message.py'):
        # 假设Message.py在同一文件夹下，并且接受一个project_name参数来启动项目
        subprocess.Popen(['python', 'Message.py', project_name])
        return jsonify({'status': 'Message started'}), 200
    else:
        return jsonify({'status': 'Message already running'}), 200

@app.route('/getHistory', methods=['GET'])
def get_history():
    project_name = request.args.get('ProjectName')
    if not project_name:
        return jsonify({'error': 'ProjectName is required'}), 400

    history_dir = 'History'
    file_path = os.path.join(history_dir, f'{project_name}.json')

    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            json_data = json.load(f)
    else:
        json_data = []

    return jsonify(json_data), 200
@app.route('/get-missing-packages')
def get_missing_packages():
    try:
        directory = 'Nodes'  # 直接指定 Nodes 文件夹
        app.logger.debug(f"Checking directory: {directory}")
        
        python_files = []
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.endswith('.py'):
                    python_files.append(os.path.join(root, file))
                    
        app.logger.debug(f"Python files found: {python_files}")
        
        all_imports = set()
        print('files:', python_files)
        for file in python_files:
            imports = find_imports(file)
            app.logger.debug(f"Imports found in {file}: {imports}")
            all_imports.update(imports)
        
        missing_packages = [package for package in all_imports if not is_installed(package)]
        app.logger.debug(f"Missing packages: {missing_packages}")
        print('missing_packages:', missing_packages)
        return jsonify(missing_packages)
    except Exception as e:
        app.logger.error(f"Error occurred: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/install-packages', methods=['POST'])
def install_packages():
    try:
        packages = request.json.get('packages', [])
        for package in packages:
            subprocess.check_call(['pip', 'install', package])
        return jsonify({'status': 'success', 'installed': packages})
    except Exception as e:
        app.logger.error(f"Error occurred during installation: {e}")
        return jsonify({'error': str(e)}), 500
@app.route('/history-project', methods=['POST'])
def set_project():
    global project_data
    return jsonify(project_data)

@app.route('/load-project', methods=['POST'])
def load_project():
    global project_data
    global project_name
    project_data = request.json
    print('project_data:', project_data)
    # 同步更新全局项目名称，便于注册到 Control Hub
    try:
        name = project_data.get('name') or project_data.get('ProjectName') or ''
        if isinstance(name, str) and name.lower().endswith('.json'):
            project_name = name[:-5]
        else:
            project_name = name
        print(f"[DEBUG] WorkTeam /load-project 设置 project_name = {project_name}")

        # 尝试通知启动中心更新该实例的项目名称
        try:
            import requests
            port = int(sys.argv[1]) if len(sys.argv) > 1 else None
            if port and project_name:
                requests.post(
                    'http://127.0.0.1:3001/hub/update-project-name',
                    json={'port': port, 'project_name': project_name},
                    timeout=2
                )
                print(f"✅ WorkTeam 已通知 Control Hub 更新项目名称: {project_name}")
        except Exception as e:
            print(f"⚠️ WorkTeam 更新 Control Hub 项目名称失败: {e}")
    except Exception as e:
        print(f"⚠️ WorkTeam /load-project 解析项目名称失败: {e}")

    return jsonify({'status': 'Project loaded successfully'})  
@app.route('/get-node-details/<node_name>')
def get_node_details(node_name):
    try:
        file_path = os.path.join('Nodes', f'{node_name}.py')  # 确保路径正确
        
        # 初始化 IsLoadSuccess 标志，假设为 True
        is_load_success = True

        # 检查文件是否存在，如果不存在直接设置 is_load_success 为 False
        if not os.path.exists(file_path):
            is_load_success = False
            return jsonify({
                "Outputs": [],
                "Inputs": [],
                "Lable": [],
                "InputIsAdd": '',
                "OutputsIsAdd": '',
                "NodeKind": '',
                "IsLoadSuccess": is_load_success  # 文件找不到时返回 false
            })
        
        # 加载节点模块
        spec = importlib.util.spec_from_file_location("node_module", file_path)
        node_module = importlib.util.module_from_spec(spec)
        sys.modules["node_module"] = node_module
        
        try:
            spec.loader.exec_module(node_module)  # 尝试加载模块
        except ModuleNotFoundError as e:
            is_load_success = False  # 如果库未找到，将标志设为 False

        # 获取 Outputs, Inputs, 和 Lable
        # 使用单独的 try-except 来确保即使加载模块失败，其他信息也可以正常获取
        Outputs = []
        Inputs = []
        Lable = []
        InputIsAdd = ''
        OutputsIsAdd = ''
        NodeKind = ''
        
        try:
            Outputs = getattr(node_module, 'Outputs', [])
        except AttributeError:
            pass  # 如果不存在 Outputs 属性，忽略错误
        
        try:
            Inputs = getattr(node_module, 'Inputs', [])
        except AttributeError:
            pass  # 如果不存在 Inputs 属性，忽略错误
        
        try:
            Lable = getattr(node_module, 'Lable', [])
        except AttributeError:
            pass  # 如果不存在 Lable 属性，忽略错误

        try:
            InputIsAdd = getattr(node_module, 'InputIsAdd', '')
        except AttributeError:
            pass  # 如果不存在 InputIsAdd 属性，忽略错误
        
        try:
            OutputsIsAdd = getattr(node_module, 'OutputsIsAdd', '')
        except AttributeError:
            pass  # 如果不存在 OutputsIsAdd 属性，忽略错误
        
        try:
            NodeKind = getattr(node_module, 'NodeKind', '')
        except AttributeError:
            pass  # 如果不存在 NodeKind 属性，忽略错误

        # 返回信息以 JSON 格式
        return jsonify({
            "Outputs": Outputs,
            "Inputs": Inputs,
            "Lable": Lable,
            "InputIsAdd": InputIsAdd,
            "OutputsIsAdd": OutputsIsAdd,
            "NodeKind": NodeKind,
            "IsLoadSuccess": is_load_success  # 返回加载库是否成功
        })
    except Exception as e:
        return jsonify({"error": str(e)})
def register_to_hub(port):
    """向启动程序注册实例（带正确的项目名称）"""
    import threading
    import os
    global project_name
    
    def register():
        import requests  # 必须在线程函数内导入
        import time
        
        print(f"[DEBUG] WorkTeam {port} 准备注册到 Control Hub...")
        time.sleep(2)  # 等待服务启动
        
        try:
            # 优先使用实际加载的项目名（例如 HistoryItem.name / New Item）
            proj_name = project_name or f'workteam_{port}'
            register_data = {
                'port': port,
                'type': 'workteam',
                'project_name': proj_name,
                'pid': os.getpid()
            }
            print(f"[DEBUG] WorkTeam {port} 注册数据: {register_data}")
            
            response = requests.post(
                'http://127.0.0.1:3001/hub/register-instance',
                json=register_data,
                timeout=5
            )
            print(f"[DEBUG] WorkTeam {port} 注册响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ WorkTeam {port} 已注册到 Control Hub: {result}")
                # 启动心跳
                start_heartbeat(port)
            else:
                print(f"⚠️ WorkTeam {port} 注册失败: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"⚠️ WorkTeam {port} 无法连接到 Control Hub: {e}")
            import traceback
            traceback.print_exc()
    
    thread = threading.Thread(target=register, daemon=True)
    thread.start()

def start_heartbeat(port):
    """定期发送心跳"""
    import threading
    
    def heartbeat():
        import requests
        import time
        
        while True:
            try:
                requests.post(
                    'http://127.0.0.1:3001/hub/heartbeat',
                    json={'port': port, 'status': 'running'},
                    timeout=2
                )
            except:
                pass
            time.sleep(10)  # 每10秒发送一次心跳
    
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()

if __name__ == '__main__':
    port = int(sys.argv[1])
    print(f"Starting server on port {port}")
    
    # 注册到 Control Hub
    register_to_hub(port)
    
    app.run(debug=True, port=port, use_reloader=False)
