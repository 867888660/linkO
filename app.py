from flask import Flask, jsonify, render_template,request
import pandas as pd
from contextlib import redirect_stdout
import io
import os
import asyncio
import hashlib
import json
import importlib.util
import sys
import subprocess
import base64
import textwrap
import ast
import traceback  # 确保已经导入traceback模块
import re
import traceback
import shutil
import importlib
import logging
import tempfile
import asyncio
import ast
import time
from pathlib import Path
from threading import Lock

from typing import Any, Dict, List, Optional
app = Flask(__name__)
project_data = {}
project_name = ''

# ==== 1. 目录常量（全部 Path 对象）====
BASE_DIR      = Path(__file__).resolve().parent        # 项目根目录
TEMP_DIR      = BASE_DIR / "TempFiles"                  # 临时文件夹
NOTEBOOK_DIR  = BASE_DIR / "NoteBook"                   # NoteBook 绝对路径
MEMORY_DIR    = BASE_DIR / "Memory"                     # Memory 绝对路径
WORKFLOW_DIR  = BASE_DIR / "WorkFlow"                   # WorkFlow 绝对路径
NODES_DIR     = BASE_DIR / "Nodes"                      # Nodes 绝对路径

# ==== 2. 确保这些目录都存在 ====
for folder in (TEMP_DIR, NOTEBOOK_DIR, MEMORY_DIR, WORKFLOW_DIR, NODES_DIR):
    folder.mkdir(parents=True, exist_ok=True)




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
def save():
    global project_data, project_name

    payload   = request.get_json(force=True)
    save_name = payload['name'].strip()
    save_data = payload['data']
    save_path = (payload.get('path') or '').strip()     # 可能为空/None

    # ---------- 目录处理 ----------
    base_dir  = Path('WorkFlow')                        # 稳定根目录

    # 1) 去掉开头可能出现的 ./  \  /  等
    rel_path  = Path(save_path).as_posix().lstrip('/\\')

    # 2) 若前端误把 'WorkFlow' 带进来了，祛除重复
    if rel_path.startswith('WorkFlow'):
        rel_path = rel_path[len('WorkFlow'):].lstrip('/\\')

    # 3) 拼完整目录
    full_dir  = base_dir / rel_path if rel_path else base_dir
    full_dir.mkdir(parents=True, exist_ok=True)         # 递归创建

    # ---------- 写文件 ----------
    file_path = full_dir / f'{save_name}.json'
    file_path.write_text(save_data, encoding='utf-8')

    # ---------- 更新全局变量 ----------
    if not isinstance(project_data, dict):
        project_data = {}

    project_data.update({
        'json_name': f'{save_name}.json',
        'json_path': str(full_dir),
        'name'     : f'{save_name}.json',
        'path'     : str(full_dir),
        'host'     : payload.get('host', ''),
        'callsign' : payload.get('callsign', '')
    })
    project_name = save_name

    return jsonify({'message': 'Save successful'})

@app.route('/')
def index():
    return render_template('index.html')
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
                            targetNode['ExportPrompt'] = export_prompt +'**n**' + targetNode.get('ExprotAfterPrompt', '')
                            print('ExportPrompt:', targetNode['ExportPrompt'])
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
        node['ExportPrompt'] = export_prompt + '**n**' + node.get('ExprotAfterPrompt', '')
        print('ExportPrompt:', node['ExportPrompt'])
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
                        targetNode['ExportPrompt'] = export_prompt +'**n**' + targetNode.get('ExprotAfterPrompt', '')
                        print('ExportPrompt:', targetNode['ExportPrompt'])
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
        node['ExportPrompt'] = export_prompt + '**n**' + node.get('ExprotAfterPrompt', '')
        print('ExportPrompt:', node['ExportPrompt'])
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
# ==== 2. 占位符解析函数 ====
def _resolve_tempfiles(ctx: str) -> str:
    """
    在多行字符串中把形如
        @TempFiles/path/to/file.txt
        @NoteBook\sub\dir
        ...
    的标记替换为 **绝对路径的 POSIX 形式**（使用正斜杠），并保证父目录存在。

    支持的标记：
        @TempFiles  @NoteBook  @Memory  @WorkFlow  @Nodes
    """
    if not isinstance(ctx, str):
        return ctx

    # 根目录映射
    DIRS: dict[str, Path] = {
        "TempFiles": Path(TEMP_DIR),
        "NoteBook":  Path(NOTEBOOK_DIR),
        "Memory":    Path(MEMORY_DIR),
        "WorkFlow":  Path(WORKFLOW_DIR),
        "Nodes":     Path(NODES_DIR),
    }

    # 动态构造正则：@Tag[/\]optional_sub_path
    tag_pattern = "|".join(map(re.escape, DIRS.keys()))
    pattern = re.compile(
        rf'@(?P<tag>{tag_pattern})(?P<sep>[\\/])?(?P<sub>[^\s;,\n\r]*)',
        flags=re.MULTILINE,
    )

    def _repl(m: re.Match) -> str:
        tag   = m.group("tag")               # TempFiles / NoteBook / ...
        sub   = m.group("sub") or ""         # 跟在标签后的子路径
        base  = DIRS[tag]

        # 把子路径按 / 或 \ 拆开再拼接
        parts = re.split(r"[\\/]", sub) if sub else []
        full  = (base.joinpath(*parts)).resolve()

        # 若有具体文件/文件夹，确保父目录存在
        if parts:
            full.parent.mkdir(parents=True, exist_ok=True)

        # 统一输出为 POSIX 样式，避免 JSON 转义麻烦
        return full.as_posix()

    return pattern.sub(_repl, ctx)
# ==== 3. 主路由 ====
# ------------------------------------------------------------
# 工具：本地图片转 Base64
# ------------------------------------------------------------
def image_to_base64(fp: str) -> str:
    fp = Path(fp).expanduser().resolve()
    with open(fp, "rb") as f:
        return base64.b64encode(f.read()).decode()

# ------------------------------------------------------------
# 主入口
# ------------------------------------------------------------
@app.route("/run-node", methods=["POST"])
def run_node_route():
    data      = request.get_json(force=True)
    node_name = data.get("name")
    node      = data.get("node", {})

    # ---------- 1. 先解析 @TempFiles、@Memory 等标签 ----------
    TAGS = ["TempFiles", "NoteBook", "Memory", "WorkFlow", "Nodes"]
    for tag in TAGS:
        marker = f"@{tag}"
        for inp in node.get("Inputs", []):
            ctx = inp.get("Context")
            if isinstance(ctx, str) and marker in ctx:
                inp["Context"] = _resolve_tempfiles(ctx)

        ex_prompt = node.get("ExportPrompt")
        if isinstance(ex_prompt, str) and marker in ex_prompt:
            node["ExportPrompt"] = _resolve_tempfiles(ex_prompt)

    # ---------- 2. 构造完整对话 messages（含图片） ----------
    # 2.1 收集需要转 Base64 的图片
    temp_images_b64 = [
        image_to_base64(inp.get("Context", ""))
        for inp in node.get("Inputs", [])
        if isinstance(inp.get("Kind"), str) and "FilePath" in inp["Kind"]
    ]

    # 2.2 system_prompt 生成
    system_prompt = f"{node.get('SystemPrompt', '')}\n{node.get('ExprotAfterPrompt', '')}"
    if node.get("OriginalTextSelector") == "OriginalText":
        system_prompt = node.get("SystemPrompt", "")

    # 2.3 拼接消息列表
    msg_list = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": node.get("ExportPrompt", "")},
        *[m for m in node.get("messages", []) if m.get("role") != "System"],
    ]
    for b64 in temp_images_b64:
        msg_list.append({
            "role": "user",
            "content": [{
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
            }]
        })

    # 2.4 写回到 node，避免覆盖旧键，改用 CombinedMessages
    node["messages"] = msg_list

    # ---------- 3. 统一结果格式处理 ----------
    def normalize_result(result):
        if isinstance(result, dict) and "outputs" in result:
            output, debug_text = result["outputs"], result.get("debug_text", "")
        else:
            output, debug_text = result, ""

        if isinstance(output, str):
            m = re.search(r"```(?:json)?\s*(.*?)\s*```", output, re.S | re.I)
            raw = m.group(1) if m else output
            try:
                output = json.loads(raw)
            except Exception:
                pass

        if isinstance(output, list) and len(output) == 1 and isinstance(output[0], list):
            output = output[0]

        if not isinstance(output, list):
            output = [output]

        return output, debug_text

    # ---------- 4. 分支：ReAct / LangGraph ----------
    node_kind = node.get("NodeKind")
    tools = node.get("Tools")
    is_react = node.get("IsReact")

    if node_kind == "LLm" and tools is not None and is_react is True:
    # your code here
        try:
            langgraph_agent_path = (BASE_DIR / "Langgraph" / "agent.py").resolve()
            if not langgraph_agent_path.is_file():
                return jsonify({"error": f"Langgraph/agent.py not found at {langgraph_agent_path}"}), 404

            with lock:
                spec   = importlib.util.spec_from_file_location("langgraph_agent", langgraph_agent_path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)

            result = module.run_node(node)
            output, debug_text = normalize_result(result)

            return jsonify({
                "output":       output,
                "debug_text":   debug_text,
                "inputs":       node.get("Inputs", []),
                "ExportPrompt": node.get("ExportPrompt"),
            })

        except Exception as e:
            return jsonify({"error": str(e), "trace": traceback.format_exc()}), 400

    # ---------- 5. 分支：普通脚本 ----------
    script_path = _find_script(node_name)
    if script_path is None or not script_path.is_file():
        return jsonify({"error": f"Script {node_name} not found"}), 404

    try:
        with lock:
            spec   = importlib.util.spec_from_file_location(script_path.stem, script_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)

        result = module.run_node(node)
        output, debug_text = normalize_result(result)

        return jsonify({
            "output":       output,
            "debug_text":   debug_text,
            "inputs":       node.get("Inputs", []),
            "ExportPrompt": node.get("ExportPrompt"),
        })

    except Exception as e:
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 400
# ==== 4. 脚本查找 ====
def _find_script(node_name: str) -> Optional[Path]:
    """
    在 Nodes 目录下查找与 node_name 匹配的脚本（大小写不敏感）：
    1) foo.py
    2) foo/__init__.py
    3) foo/main.py
    """
    base = node_name[:-3] if node_name.lower().endswith(".py") else node_name
    candidates = [
        f"{base}.py",            # foo.py
        f"{base}/__init__.py",   # foo/__init__.py
        f"{base}/main.py",       # foo/main.py
    ]

    for cand in candidates:
        p = (NODES_DIR / cand).resolve()
        if p.is_file():
            return p

    # 兼容 macOS/Linux 的大小写差异：遍历一次
    lower_target_names = {Path(c).name.lower() for c in candidates}
    for p in NODES_DIR.rglob("*"):
        if p.is_file() and p.name.lower() in lower_target_names:
            return p

    return None
@app.route('/read_DataBase', methods=['POST'])
def read_data():
    try:
        # 获取文件路径
        data = request.get_json()
        if 'file_path' not in data:
            return jsonify({'status': 'fail', 'message': 'No file path provided in the request'})

        file_path = _resolve_tempfiles(data['file_path'])
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            return jsonify({'status': 'fail', 'message': 'File not found'})

        response_data = {}
        columns_data = {}  # 用于存储每个 sheet 的列名
        file_ext = os.path.splitext(file_path)[1].lower()

        # 根据文件类型进行处理
        if file_ext == '.xlsx':
            # 处理 Excel 文件
            try:
                excel_data = pd.ExcelFile(file_path)
                for sheet_name in excel_data.sheet_names:
                    df = excel_data.parse(sheet_name)

                    # 替换未命名的列，添加序号和列标签
                    df.columns = [
                        f"{i+1}/{get_excel_column_label(i)}/{col if 'Unnamed' not in str(col) else 'Unnamed'}"
                        for i, col in enumerate(df.columns)
                    ]

                    # 自定义排序规则
                    def sort_key(col_name):
                        parts = col_name.split('/')
                        num_part = int(parts[0])  # 序号作为整数
                        letter_part = parts[1]  # Excel 样式的列标
                        name_part = parts[2]  # 原始名称或 'Unnamed'
                        return num_part, letter_part, name_part

                    # 对列进行排序
                    sorted_columns = sorted(df.columns, key=sort_key)
                    df = df[sorted_columns]

                    # 将 DataFrame 中的 NaN 值替换为 "Empty" 字符串，以避免 JSON 转换问题
                    df = df.fillna("Empty")

                    # 将 DataFrame 转换为字典格式
                    response_data[sheet_name] = df.to_dict(orient='records')
                    
                    # 存储列名
                    columns_data[sheet_name] = df.columns.tolist()

            except Exception as e:
                return jsonify({'status': 'fail', 'message': f'Error processing Excel file: {str(e)}'})

        elif file_ext in ['.json', '.jsonl']:
            # 处理 JSON/JSONL 文件
            try:
                json_data = []
                
                if file_ext == '.json':
                    # 处理标准JSON文件
                    with open(file_path, 'r', encoding='utf-8') as json_file:
                        data_content = json.load(json_file)
                        if isinstance(data_content, list):
                            json_data = data_content
                        else:
                            json_data = [data_content]
                
                elif file_ext == '.jsonl':
                    # 处理JSONL文件（每行一个JSON对象）
                    with open(file_path, 'r', encoding='utf-8') as jsonl_file:
                        for line in jsonl_file:
                            line = line.strip()
                            if line:
                                try:
                                    json_data.append(json.loads(line))
                                except json.JSONDecodeError as line_error:
                                    # 跳过无效的JSON行，但记录错误
                                    logging.warning(f'Skipping invalid JSON line: {line}, Error: {str(line_error)}')
                                    continue
                
                # 统一使用'default'作为sheet名，忽略sheet参数
                sheet_name = 'default'
                response_data[sheet_name] = json_data
                
                # 获取所有可能的列名（合并所有对象的键）
                all_columns = set()
                for item in json_data:
                    if isinstance(item, dict):
                        all_columns.update(item.keys())
                
                # 将列名转换为列表并排序，保持一致性
                columns_data[sheet_name] = sorted(list(all_columns))
                
            except json.JSONDecodeError as json_error:
                return jsonify({'status': 'fail', 'message': f'Invalid JSON format: {str(json_error)}'})
            except Exception as e:
                return jsonify({'status': 'fail', 'message': f'Error reading JSON/JSONL file: {str(e)}'})

        else:
            return jsonify({'status': 'fail', 'message': 'Invalid file type. Only .xlsx, .json, and .jsonl are allowed.'})

        return jsonify({'status': 'success', 'data': response_data, 'columns': columns_data})

    except Exception as e:
        return jsonify({'status': 'fail', 'message': str(e)})

# ==== Excel 工具函数 =================================================
def get_excel_column_label(index: int) -> str:
    """
    0‑based 列号  ➜  Excel 标签：
        0 → A, 1 → B, … 25 → Z, 26 → AA …
    """
    label = ""
    index += 1                       # 变成 1‑based
    while index:
        index, rem = divmod(index - 1, 26)
        label = chr(65 + rem) + label
    return label

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
    os.makedirs(folder_path, exist_ok=True)

    file_hashes = []
    for fn in os.listdir(folder_path):
        if fn.endswith('.py'):
            fp = os.path.join(folder_path, fn)
            file_hashes.append({
                "Filename":  fn,
                "Hash":      hash_file(fp),
                "NodeKind":  extract_node_kind(fp),
                "NodeFunction": extract_node_function(fp)   # 建议返回真实换行
            })

    # ---------- ① 保存 json ----------
    json_path = os.path.join(folder_path, 'jsonlist.json')
    with open(json_path, 'w', encoding='utf-8') as jf:
        json.dump(file_hashes, jf, indent=4, ensure_ascii=False)

    # ---------- ② 保存 jsonl ----------
    jsonl_path = os.path.join(folder_path, 'jsonlist.jsonl')
    with open(jsonl_path, 'w', encoding='utf-8') as jl:
        for item in file_hashes:
            jl.write(json.dumps({
                "id":   item["Filename"],
                "text": item["NodeFunction"],
                "node_kind": item["NodeKind"]
            }, ensure_ascii=False) + '\n')

    # 如果只是返回给前端，内存里的 file_hashes 就够用
    return jsonify([{
        'filename':      i['Filename'],
        'hash':          i['Hash'],
        'NodeKind':      i['NodeKind'],
        'NodeFunction':  i['NodeFunction']
    } for i in file_hashes])


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
    data = request.get_json(force=True)
    # 1. 参数校验
    if not data or 'json_path' not in data or 'json_name' not in data:
        return jsonify({'error': 'json_path 或 json_name 未提供'}), 400

    # 2. 规范化路径分隔符
    print(f"Original json_path测试: {data['json_path']}")
    path = data['json_path'].replace('\\', '/').strip('/')
    # 3. 确保以 WorkFlow/ 开头
    if not path.startswith('WorkFlow/') and not path.startswith('WorkFlow'):
        path = f'WorkFlow/{path}'
    print(f"Normalized json_path测试: {path}")
    folder_path = path  # 这时一定已被赋值

    # 4. 构造文件全路径
    json_name = data['json_name']
    file_path = os.path.join(folder_path, json_name)

    # 5. 检查文件是否存在
    if not os.path.isfile(file_path):
        return jsonify({'error': 'File not found', 'path': file_path}), 404

    # 6. 返回 JSON 内容
    with open(file_path, 'r', encoding='utf-8') as f:
        file_data = json.load(f)
    return jsonify(file_data)
@app.route('/browse', methods=['POST'])
def browse_directory():
    dir_path = request.json.get('path', '.')  # 获取请求中的路径，如果没有提供则默认为当前目录

    # 检查路径是否包含'@TempFiles'
    if '@TempFiles' in dir_path:
        # 这里假设根目录下和当前目录下都有一个TempFiles文件夹
        # 你可以根据实际情况调整这些路径
        root_temp_path = os.path.join(os.path.abspath(os.sep), 'TempFiles')
        current_temp_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'TempFiles')
        
        # 选择一个实际存在的路径
        if os.path.exists(root_temp_path):
            actual_path = root_temp_path
        elif os.path.exists(current_temp_path):
            actual_path = current_temp_path
        else:
            error_message = f"'TempFiles' directory not found in expected locations."
            logging.error(error_message)
            return jsonify({'error': error_message}), 404
        
        # 替换'@TempFiles'为实际路径
        dir_path = dir_path.replace('@TempFiles', actual_path)
    if '@NoteBook' in dir_path:
        # 这里假设根目录下和当前目录下都有一个TempFiles文件夹
        # 你可以根据实际情况调整这些路径
        root_temp_path = os.path.join(os.path.abspath(os.sep), 'NoteBook')
        current_temp_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'NoteBook')

        # 选择一个实际存在的路径
        if os.path.exists(root_temp_path):
            actual_path = root_temp_path
        elif os.path.exists(current_temp_path):
            actual_path = current_temp_path
        else:
            error_message = f"'NoteBook' directory not found in expected locations."
            logging.error(error_message)
            return jsonify({'error': error_message}), 404
        # 替换'@TempFiles'为实际路径
        dir_path = dir_path.replace('@NoteBook', actual_path)
    if '@Memory' in dir_path:
        # 这里假设根目录下和当前目录下都有一个TempFiles文件夹
        # 你可以根据实际情况调整这些路径
        root_temp_path = os.path.join(os.path.abspath(os.sep), 'Memory')
        current_temp_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'Memory')

        # 选择一个实际存在的路径
        if os.path.exists(root_temp_path):
            actual_path = root_temp_path
        elif os.path.exists(current_temp_path):
            actual_path = current_temp_path
        else:
            error_message = f"'Memory' directory not found in expected locations."
            logging.error(error_message)
            return jsonify({'error': error_message}), 404
        # 替换'@TempFiles'为实际路径
        dir_path = dir_path.replace('@Memory', actual_path)
    if '@Nodes' in dir_path:
        # 这里假设根目录下和当前目录下都有一个Nodes文件夹
        root_temp_path = os.path.join(os.path.abspath(os.sep), 'Nodes')
        current_temp_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'Nodes')

        # 选择一个实际存在的路径
        if os.path.exists(root_temp_path):
            actual_path = root_temp_path
        elif os.path.exists(current_temp_path):
            actual_path = current_temp_path
        else:
            error_message = f"'Nodes' directory not found in expected locations."
            logging.error(error_message)
            return jsonify({'error': error_message}), 404
        # 替换'@Nodes'为实际路径
        dir_path = dir_path.replace('@Nodes', actual_path)
    if '@WorkFlow' in dir_path:
        # 这里假设根目录下和当前目录下都有一个WorkFlow文件夹
        root_temp_path = os.path.join(os.path.abspath(os.sep), 'WorkFlow')
        current_temp_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'WorkFlow')

        # 选择一个实际存在的路径
        if os.path.exists(root_temp_path):
            actual_path = root_temp_path
        elif os.path.exists(current_temp_path):
            actual_path = current_temp_path
        else:
            error_message = f"'WorkFlow' directory not found in expected locations."
            logging.error(error_message)
            return jsonify({'error': error_message}), 404
        # 替换'@WorkFlow'为实际路径
        dir_path = dir_path.replace('@WorkFlow', actual_path)
        
    else:
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
            # 这里保持返回的路径显示为'@TempFiles'、'@WorkFlow'、'@Nodes'、'@Memory'、'@NoteBook'，如果原始路径中包含这些特殊前缀
            original_path = request.json.get('path', '.')
            display_path = item_path
            if '@TempFiles' in original_path:
                display_path = item_path.replace(actual_path, '@TempFiles')
            elif '@WorkFlow' in original_path:
                display_path = item_path.replace(actual_path, '@WorkFlow')
            elif '@Nodes' in original_path:
                display_path = item_path.replace(actual_path, '@Nodes')
            elif '@Memory' in original_path:
                display_path = item_path.replace(actual_path, '@Memory')
            elif '@NoteBook' in original_path:
                display_path = item_path.replace(actual_path, '@NoteBook')
            items.append({
                'name': item,
                'is_dir': os.path.isdir(item_path),  # 判断是否是文件夹
                'path': display_path
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
@app.route('/workflow-files')
def get_workflow_files():
    # 确保从正确的根目录开始搜索
    workflow_path = "WorkFlow"  # 使用相对路径，与保存逻辑一致
    
    # 确保WorkFlow文件夹存在
    if not os.path.exists(workflow_path):
        return jsonify([])
    
    workflow_files = []
    
    # 遍历WorkFlow文件夹及其子文件夹
    for root, dirs, files in os.walk(workflow_path):
        for file in files:
            if file.endswith('.json'):  # 只获取Python文件
                # 计算相对于WorkFlow文件夹的路径
                relative_path = os.path.relpath(root, workflow_path)
                folder_name = relative_path if relative_path != '.' else ''
                
                # 构建文件信息
                file_info = {
                    'filename': file,
                    'filepath': os.path.join(relative_path, file).replace('\\', '/'),
                    'folder': folder_name.replace('\\', '/')
                }
                workflow_files.append(file_info)
                
                print(f"Found file: {file_info}")  # 添加调试输出
    
    print(f"Total files found: {len(workflow_files)}")  # 添加调试输出
    return jsonify(workflow_files)


def safe_write_json(file_path, data, max_retries=3):
    for attempt in range(max_retries):
        try:
            # 在 Windows 上使用 'w' 模式会自动获取独占写入权限
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"❌ Write attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(0.5)  # 重试前等待
            continue
    return False

@app.route('/addHistory', methods=['POST'])
def add_history():
    data = request.json
    project_name = request.args.get('ProjectName')
    
    # 验证项目名称是否存在
    if not project_name:
        return jsonify({'error': 'ProjectName is required'}), 400

    # 验证收到的数据是否为字典（JSON对象）
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid data format. Expected a JSON object.'}), 400

    history_dir = 'History'
    if not os.path.exists(history_dir):
        os.makedirs(history_dir)
    
    # 确保文件名带有 .json 扩展名
    file_path = os.path.join(history_dir, f'{project_name}.json')
    print(f"📄 File path: {file_path}")

    # 尝试读取现有的JSON文件
    if os.path.exists(file_path):
        for attempt in range(3):  # 添加重试机制
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                print(f"✅ Existing data loaded from {file_path}")
                break
            except json.JSONDecodeError as e:
                print(f"❌ JSON decode error: {e}")
                # 如果文件损坏，创建备份
                if os.path.getsize(file_path) > 0:
                    backup_path = f"{file_path}.backup.{int(time.time())}"
                    try:
                        os.rename(file_path, backup_path)
                        print(f"📦 Created backup of corrupted file: {backup_path}")
                    except Exception as e:
                        print(f"⚠️ Failed to create backup: {e}")
                json_data = []
                break
            except Exception as e:
                print(f"❌ Read attempt {attempt + 1} failed: {e}")
                if attempt == 2:  # 最后一次尝试失败
                    json_data = []
                else:
                    time.sleep(0.5)  # 等待后重试
    else:
        print(f"ℹ️ No existing data. Initializing new data array.")
        json_data = []

    # 确保 json_data 是一个列表
    if not isinstance(json_data, list):
        print("⚠️ json_data is not a list. Initializing as empty list.")
        json_data = []

    # 将数据添加到现有的最后一个数组中
    if not json_data or not isinstance(json_data[-1], list):
        print("📝 Appending new sublist to json_data.")
        json_data.append([])

    print(f"➕ Adding data to json_data[-1]: {data}")
    json_data[-1].append(data)

    # 使用安全写入函数保存数据
    if safe_write_json(file_path, json_data):
        print("✅ Data added successfully.")
        return jsonify({'message': 'Data added successfully'}), 200
    else:
        print("❌ Failed to write data after multiple attempts")
        return jsonify({'error': 'Failed to save data after multiple attempts'}), 500

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
    file_path = os.path.join(history_dir, project_name)
    # 检查文件是否存在
    if not os.path.exists(file_path):
        return jsonify([]), 200  # 如果文件不存在，返回空数组
    try:
        # 尝试以 UTF-8 编码读取文件
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
    except UnicodeDecodeError:
        return jsonify({'error': 'File encoding is not UTF-8. Please ensure the file is saved as UTF-8.'}), 500
    except json.JSONDecodeError:
        return jsonify({'error': 'File content is not valid JSON.'}), 500
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
    print('project_data测试:', project_data)
    return jsonify(project_data)

@app.route('/load-project', methods=['POST'])
def load_project():
    global project_data
    global project_name
    project_data = request.json
    print('project_data:', project_data)
    # 在这里处理项目数据，例如保存到数据库或加载到内存中
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
if __name__ == '__main__':
    port = int(sys.argv[1])
    print(f"Starting server on port {port}")
    app.run(debug=True, port=port, use_reloader=False)
