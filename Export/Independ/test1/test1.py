from flask import Flask, jsonify, request
import hashlib
import json
import os
import re
import sys
import traceback
OutPutNum = 2
InPutNum = 4
Outputs = [{'Num': None, 'Kind': 'Num', 'Id': 'Add.py1714968318605_2', 'Context': None,'Boolean': False,'name': 'OutPut1','Link':0,'Description':'answer'}, {'Num': None, 'Kind': 'Num', 'Id': 'Add.py1714968319615_2', 'Context': None,'Boolean': False,'name': 'OutPut1','Link':0,'Description':'answer'}]
Inputs = [{'Num': None, 'Context': '', 'Boolean': False, 'Kind': 'Num', 'Id': 'Input1', 'IsLabel': False, 'name': 'Input1'}, {'Num': None, 'Context': '', 'Boolean': False, 'Kind': 'Num', 'Id': 'Input2', 'IsLabel': False, 'name': 'Input2'}, {'Num': None, 'Context': '', 'Boolean': False, 'Kind': 'Num', 'Id': 'Input3', 'IsLabel': False, 'name': 'Input1'}, {'Num': None, 'Context': '', 'Boolean': False, 'Kind': 'Num', 'Id': 'Input4', 'IsLabel': False, 'name': 'Input2'}]
NodeKind = 'Normal'
nodes = [{"id": "Add.py1714968318605", "name": "Add.py", "label": "Add.py0", "hash": "b674dbca8e7bfc6fa675e78f8e1e840c7e26a7d1bf2ecdf24fd6eec2bcccd457", "x": 521, "y": 164, "TriggerLink": 0, "IsHovor": False, "IsBlock": False, "IsRunning": False, "isFinish": False, "IsError": False, "IsTrigger": False, "ErrorContext": "", "prompt": "", "ExprotPrompt": "", "ExprotAfterPrompt": "", "anchorPoints": [[0.036302187348593175, 0.6], [0.036302187348593175, 0.8], [0.9576474480933079, 0.6], [0.06050364558098862, 0.1]], "Inputs": [{"Context": None, "Id": "Input1", "IsLabel": False, "Isnecessary": True, "Kind": "Num", "Link": 0, "Num": None, "name": "Input1"}, {"Context": None, "Id": "Input2", "IsLabel": False, "Isnecessary": True, "Kind": "Num", "Link": 0, "Num": None, "name": "Input2"}], "Lable": [{"Id": "Label1", "Kind": "None"}], "NodeKind": "Normal", "Outputs": [{"Context": None, "Id": "Output11", "Kind": "Num", "Link": 0, "Num": None, "name": "OutPut1"}], "type": "fileNode", "style": {"hover": {"fill": "lightgreen"}, "active": {"stroke": "#ff0000", "lineWidth": 100}}, "draggable": False, "height": 40, "width": 165.279296875, "depth": 0}, {"id": "Add.py1714968319615", "name": "Add.py", "label": "Add.py1", "hash": "b674dbca8e7bfc6fa675e78f8e1e840c7e26a7d1bf2ecdf24fd6eec2bcccd457", "x": 437, "y": 184, "TriggerLink": 0, "IsHovor": False, "IsBlock": False, "IsRunning": False, "isFinish": False, "IsError": False, "IsTrigger": False, "ErrorContext": "", "prompt": "", "ExprotPrompt": "", "ExprotAfterPrompt": "", "anchorPoints": [[0.036302187348593175, 0.6], [0.036302187348593175, 0.8], [0.9576474480933079, 0.6], [0.06050364558098862, 0.1]], "Inputs": [{"Context": None, "Id": "Input1", "IsLabel": False, "Isnecessary": True, "Kind": "Num", "Link": 0, "Num": None, "name": "Input1"}, {"Context": None, "Id": "Input2", "IsLabel": False, "Isnecessary": True, "Kind": "Num", "Link": 0, "Num": None, "name": "Input2"}], "Lable": [{"Id": "Label1", "Kind": "None"}], "NodeKind": "Normal", "Outputs": [{"Context": None, "Id": "Output11", "Kind": "Num", "Link": 0, "Num": None, "name": "OutPut1"}], "type": "fileNode", "style": {"hover": {"fill": "lightgreen"}, "active": {"stroke": "#ff0000", "lineWidth": 100}}, "draggable": False, "height": 40, "width": 165.279296875, "depth": 0}]
edges = []
unconnected_inputs = [{"source": None, "sourceAnchor": None, "target": "Add.py1714968318605", "anchorIndex": 0, "name": "Input1", "IsLabel": False, "Kind": "Num", "Num": None, "Context": "", "Boolean": False}, {"source": None, "sourceAnchor": None, "target": "Add.py1714968318605", "anchorIndex": 1, "name": "Input2", "IsLabel": False, "Kind": "Num", "Num": None, "Context": "", "Boolean": False}, {"source": None, "sourceAnchor": None, "target": "Add.py1714968319615", "anchorIndex": 0, "name": "Input1", "IsLabel": False, "Kind": "Num", "Num": None, "Context": "", "Boolean": False}, {"source": None, "sourceAnchor": None, "target": "Add.py1714968319615", "anchorIndex": 1, "name": "Input2", "IsLabel": False, "Kind": "Num", "Num": None, "Context": "", "Boolean": False}]
unconnected_outputs = [{"source": "Add.py1714968318605", "anchorIndex": 2, "target": None, "targetAnchor": None, "name": "OutPut1"}, {"source": "Add.py1714968319615", "anchorIndex": 2, "target": None, "targetAnchor": None, "name": "OutPut1"}]
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
            temp = 'Please ensure the output is in JSON format\n{\n'
            for index, output in enumerate(node['ExprotAfterPrompt']):
                kind = ''
                if output['Kind'] == 'String':
                    kind = 'String'
                elif output['Kind'] == 'Num':
                    kind = 'Num'
                elif output['Kind'] == 'Boolean':
                    kind = 'Boolean'
                temp += f'"{output["Id"]}": "{output["Description"]}" (you need output type:{kind})\n'
            temp += '}\n'
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
        node['ExprotPrompt'] = export_prompt + '\n' + node.get('ExprotAfterPrompt', '')
        print('ExprotPrompt:', node['ExprotPrompt'])
        if not node.get('IsTrigger', False):
            execute_node(node)
    return Outputs
def retrieve_content_within_braces(text):
    return re.findall(r'{{(.*?)}}', text)
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
                                temp = 'Please ensure the output is in JSON format\n{\n'
                                for index, output in enumerate(targetNode['ExprotAfterPrompt']):
                                    kind = ''
                                    if output['Kind'] == 'String':
                                        kind = 'String'
                                    elif output['Kind'] == 'Num':
                                        kind = 'Num'
                                    elif output['Kind'] == 'Boolean':
                                        kind = 'Boolean'
                                    temp += f'"{output["Id"]}": "{output["Description"]}" (you need output type:{kind})\n'
                                temp += '}\n'
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
                            targetNode['ExprotPrompt'] = export_prompt +'\n' + targetNode.get('ExprotAfterPrompt', '')
                            print('ExprotPrompt:', targetNode['ExprotPrompt'])
                            if not targetNode.get('IsTrigger', False):
                                execute_node(targetNode)
            else:
                print(f"Error executing node: {response.get_json()['error']}")
        else:
            print(f"Function {node_function_name} not found")