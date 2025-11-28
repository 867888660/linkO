from flask import Flask, jsonify, request
import hashlib
import json
import os
import re
import sys
import traceback
OutPutNum = 3
InPutNum = 5
Outputs = [{'Num': None, 'Kind': 'String', 'Id': 'Gpt.py1714968515288_2', 'Context': None,'Boolean': False,'name': 'Output2','Link':0,'Description':'answer'}, {'Num': None, 'Kind': 'Num', 'Id': 'Add.py1714968620863_2', 'Context': None,'Boolean': False,'name': 'OutPut1','Link':0,'Description':'answer'}, {'Num': None, 'Kind': 'Num', 'Id': 'Add.py1714968634039_2', 'Context': None,'Boolean': False,'name': 'OutPut1','Link':0,'Description':'answer'}]
Inputs = [{'Num': None, 'Context': '', 'Boolean': False, 'Kind': 'String', 'Id': 'Input1', 'IsLabel': True, 'name': 'Input1'}, {'Num': 1, 'Context': '', 'Boolean': False, 'Kind': 'Num', 'Id': 'Input2', 'IsLabel': True, 'name': 'Input1'}, {'Num': 0, 'Context': '', 'Boolean': False, 'Kind': 'Num', 'Id': 'Input3', 'IsLabel': True, 'name': 'Input2'}, {'Num': 0, 'Context': '', 'Boolean': False, 'Kind': 'Num', 'Id': 'Input4', 'IsLabel': True, 'name': 'Input1'}, {'Num': 0, 'Context': '', 'Boolean': False, 'Kind': 'Num', 'Id': 'Input5', 'IsLabel': True, 'name': 'Input2'}]
NodeKind = 'Normal'
nodes = [{"id": "IfNode.py1714968510792", "name": "IfNode.py", "label": "IfNode.py0", "hash": "2e72f423b86ccef76144b09929ade4000e18e10d3146be24f54f6922809c0981", "x": 721, "y": 218, "TriggerLink": 0, "IsHovor": False, "IsBlock": True, "IsRunning": False, "isFinish": True, "IsError": False, "IsTrigger": False, "ErrorContext": "", "prompt": "", "ExprotPrompt": "\nPlease ensure the output is in JSON format\n{\n\"Output1\":\"\"(you need output type:)\n\"Output21714968566510\":\"undefined\"(you need output type:)\n}\n", "ExprotAfterPrompt": "Please ensure the output is in JSON format\n{\n\"Output1\":\"\"(you need output type:)\n\"Output21714968566510\":\"undefined\"(you need output type:)\n}\n", "anchorPoints": [[0.03622667141512794, 0.6], [0.9577355500156841, 0.6], [0.9577355500156841, 0.8], [0.0603777856918799, 0.1]], "Inputs": [{"Num": 0, "Kind": "Boolean", "Id": "Input11714968555260", "Context": "", "Isnecessary": False, "name": "Input1", "Link": 1, "IsLabel": False, "isConnected": False, "Boolean": False}], "Lable": [{"Id": "Label1", "Kind": "None"}], "NodeKind": "IfNode", "Outputs": [{"Boolean": False, "Context": "", "Description": "", "Id": "Output1", "Kind": "Trigger", "Link": 1, "Num": 0, "name": "OutPut1", "selectBox1": "Input1", "selectBox2": "True", "selectBox3": None, "selectKind": "Boolean", "selectNum": 0}, {"Num": 0, "Kind": "Trigger", "Id": "Output21714968566510", "Context": "", "Boolean": True, "Isnecessary": True, "name": "Output2", "Link": 1, "IsLabel": False, "selectBox1": "Input1", "selectBox2": "False", "selectBox3": None, "selectKind": "Boolean", "selectNum": 0}], "type": "fileNode", "style": {"hover": {"fill": "lightgreen"}, "active": {"stroke": "#ff0000", "lineWidth": 100}}, "draggable": False, "height": 40, "width": 165.623828125, "depth": 0, "inputStatus": [True], "firstRun": True}, {"id": "Gpt.py1714968515288", "name": "Gpt.py", "label": "Gpt.py1", "hash": "845dd5010b5fcbfa596c33dfc641cd0320d5519cfa4769ab01d1207ed4066a7a", "x": 458, "y": 218, "TriggerLink": 0, "IsHovor": False, "IsBlock": True, "IsRunning": False, "isFinish": True, "IsError": False, "IsTrigger": False, "ErrorContext": "", "prompt": "{{Input1}}\u662f\u54fa\u4e73\u52a8\u7269\u5417?", "ExprotPrompt": "\u4eba\u662f\u54fa\u4e73\u52a8\u7269\u5417?\nPlease ensure the output is in JSON format\n{\n\"Output1\":\"\u662f\u54fa\u4e73\u52a8\u7269\u5219\u4e3aTrue,\u53cd\u4e4b\u4e3aFalse\"(you need output type:Boolean)\n\"Output21714968775380\":\"\u8bf4\u8bf4\u4f60\u5224\u5b9a\u7684\u4f9d\u636e\"(you need output type:String)\n}\n", "ExprotAfterPrompt": "Please ensure the output is in JSON format\n{\n\"Output1\":\"\u662f\u54fa\u4e73\u52a8\u7269\u5219\u4e3aTrue,\u53cd\u4e4b\u4e3aFalse\"(you need output type:Boolean)\n\"Output21714968775380\":\"\u8bf4\u8bf4\u4f60\u5224\u5b9a\u7684\u4f9d\u636e\"(you need output type:String)\n}\n", "anchorPoints": [[0.031240720326400444, 0.6], [0.9635524929525329, 0.6], [0.9635524929525329, 0.8], [0.052067867210667404, 0.1]], "Inputs": [{"Num": None, "Kind": "String", "Id": "Input11714968534128", "Context": "\u4eba", "Isnecessary": False, "name": "Input1", "Link": 0, "IsLabel": True, "isConnected": False}], "Lable": [{"Id": "Label1", "Kind": "None"}], "NodeKind": "LLm", "Outputs": [{"Boolean": False, "Context": "", "Description": "\u662f\u54fa\u4e73\u52a8\u7269\u5219\u4e3aTrue,\u53cd\u4e4b\u4e3aFalse", "Id": "Output1", "Kind": "Boolean", "Link": 1, "Num": 0, "name": "OutPut1"}, {"Num": 0, "Kind": "String", "Id": "Output21714968775380", "Context": "", "Boolean": False, "Isnecessary": True, "name": "Output2", "Link": 0, "IsLabel": False, "Description": "\u8bf4\u8bf4\u4f60\u5224\u5b9a\u7684\u4f9d\u636e"}], "type": "fileNode", "style": {"hover": {"fill": "lightgreen"}, "active": {"stroke": "#ff0000", "lineWidth": 100}}, "draggable": False, "height": 40, "width": 192.05703125, "depth": 0, "inputStatus": [False], "firstRun": False}, {"id": "Add.py1714968620863", "name": "Add.py", "label": "Add.py2", "hash": "b674dbca8e7bfc6fa675e78f8e1e840c7e26a7d1bf2ecdf24fd6eec2bcccd457", "x": 997, "y": 194, "TriggerLink": 1, "IsHovor": False, "IsBlock": True, "IsRunning": False, "isFinish": False, "IsError": False, "IsTrigger": True, "ErrorContext": "", "prompt": "", "ExprotPrompt": "\nPlease ensure the output is in JSON format\n{\n\"Output11\":\"undefined\"(you need output type:Num)\n}\n", "ExprotAfterPrompt": "Please ensure the output is in JSON format\n{\n\"Output11\":\"undefined\"(you need output type:Num)\n}\n", "anchorPoints": [[0.033892246486658235, 0.6], [0.033892246486658235, 0.8], [0.9604590457655654, 0.6], [0.05648707747776373, 0.1]], "Inputs": [{"Context": None, "Id": "Input1", "IsLabel": True, "Isnecessary": True, "Kind": "Num", "Link": 0, "Num": 1, "name": "Input1", "isConnected": False}, {"Context": None, "Id": "Input2", "IsLabel": True, "Isnecessary": True, "Kind": "Num", "Link": 0, "Num": 0, "name": "Input2", "isConnected": False}], "Lable": [{"Id": "Label1", "Kind": "None"}], "NodeKind": "Normal", "Outputs": [{"Context": "", "Id": "Output11", "Kind": "Num", "Link": 0, "Num": 0, "name": "OutPut1"}], "type": "fileNode", "style": {"hover": {"fill": "lightgreen"}, "active": {"stroke": "#ff0000", "lineWidth": 100}}, "draggable": False, "height": 40, "width": 177.031640625, "depth": 0, "inputStatus": [False, False], "firstRun": True}, {"id": "Add.py1714968634039", "name": "Add.py", "label": "Add.py3", "hash": "b674dbca8e7bfc6fa675e78f8e1e840c7e26a7d1bf2ecdf24fd6eec2bcccd457", "x": 994, "y": 363, "TriggerLink": 1, "IsHovor": False, "IsBlock": True, "IsRunning": False, "isFinish": True, "IsError": False, "IsTrigger": False, "ErrorContext": "", "prompt": "", "ExprotPrompt": "\nPlease ensure the output is in JSON format\n{\n\"Output11\":\"undefined\"(you need output type:Num)\n}\n", "ExprotAfterPrompt": "Please ensure the output is in JSON format\n{\n\"Output11\":\"undefined\"(you need output type:Num)\n}\n", "anchorPoints": [[0.033892246486658235, 0.6], [0.033892246486658235, 0.8], [0.9604590457655654, 0.6], [0.05648707747776373, 0.1]], "Inputs": [{"Context": None, "Id": "Input1", "IsLabel": True, "Isnecessary": True, "Kind": "Num", "Link": 0, "Num": 0, "name": "Input1", "isConnected": False}, {"Context": None, "Id": "Input2", "IsLabel": True, "Isnecessary": True, "Kind": "Num", "Link": 0, "Num": 0, "name": "Input2", "isConnected": False}], "Lable": [{"Id": "Label1", "Kind": "None"}], "NodeKind": "Normal", "Outputs": [{"Context": "", "Id": "Output11", "Kind": "Num", "Link": 0, "Num": 0, "name": "OutPut1"}], "type": "fileNode", "style": {"hover": {"fill": "lightgreen"}, "active": {"stroke": "#ff0000", "lineWidth": 100}}, "draggable": False, "height": 40, "width": 177.031640625, "depth": 0, "inputStatus": [False, False, None, True], "firstRun": True}]
edges = [{"source": "Gpt.py1714968515288", "target": "IfNode.py1714968510792", "type": "line-dash", "style": {"active": {"stroke": "rgb(95, 149, 255)", "lineWidth": 1}, "selected": {"stroke": "rgb(95, 149, 255)", "lineWidth": 2, "shadowColor": "rgb(95, 149, 255)", "shadowBlur": 10, "text-shape": {"fontWeight": 500}}, "highlight": {"stroke": "rgb(95, 149, 255)", "lineWidth": 2, "text-shape": {"fontWeight": 500}}, "inactive": {"stroke": "rgb(234, 234, 234)", "lineWidth": 1}, "disable": {"stroke": "rgb(245, 245, 245)", "lineWidth": 1}, "lineWidth": 3, "stroke": "#000", "endArrow": {"path": "M 0,0 L 12,6 L 12,-6 Z", "fill": "#5c95ff", "d": -10}}, "id": "edge-0.86463432050845461714968560485", "startPoint": {"x": 643.5205837429526, "y": 278.1, "anchorIndex": 1}, "endPoint": {"x": 726.5362266714151, "y": 278.1, "anchorIndex": 0}, "curveOffset": [-20, 20], "curvePosition": [0.5, 0.5], "sourceAnchor": 1, "targetAnchor": 0, "sourceAnchorID": "Output1", "targetAnchorID": "Input11714968555260", "depth": 0}, {"source": "IfNode.py1714968510792", "target": "Add.py1714968620863", "type": "line-dash", "style": {"active": {"stroke": "rgb(95, 149, 255)", "lineWidth": 1}, "selected": {"stroke": "rgb(95, 149, 255)", "lineWidth": 2, "shadowColor": "rgb(95, 149, 255)", "shadowBlur": 10, "text-shape": {"fontWeight": 500}}, "highlight": {"stroke": "rgb(95, 149, 255)", "lineWidth": 2, "text-shape": {"fontWeight": 500}}, "inactive": {"stroke": "rgb(234, 234, 234)", "lineWidth": 1}, "disable": {"stroke": "rgb(245, 245, 245)", "lineWidth": 1}, "lineWidth": 3, "stroke": "#000", "endArrow": {"path": "M 0,0 L 12,6 L 12,-6 Z", "fill": "#5c95ff", "d": -10}}, "id": "edge-0.4780581211480571714968651782", "startPoint": {"x": 880.0815636750158, "y": 278.1, "anchorIndex": 1}, "endPoint": {"x": 1006.5564870774778, "y": 203.6, "anchorIndex": 3}, "curveOffset": [-20, 20], "curvePosition": [0.5, 0.5], "sourceAnchor": 1, "targetAnchor": 3, "sourceAnchorID": "Output1", "depth": 0}, {"source": "IfNode.py1714968510792", "target": "Add.py1714968634039", "type": "line-dash", "style": {"active": {"stroke": "rgb(95, 149, 255)", "lineWidth": 1}, "selected": {"stroke": "rgb(95, 149, 255)", "lineWidth": 2, "shadowColor": "rgb(95, 149, 255)", "shadowBlur": 10, "text-shape": {"fontWeight": 500}}, "highlight": {"stroke": "rgb(95, 149, 255)", "lineWidth": 2, "text-shape": {"fontWeight": 500}}, "inactive": {"stroke": "rgb(234, 234, 234)", "lineWidth": 1}, "disable": {"stroke": "rgb(245, 245, 245)", "lineWidth": 1}, "lineWidth": 3, "stroke": "#000", "endArrow": {"path": "M 0,0 L 12,6 L 12,-6 Z", "fill": "#5c95ff", "d": -10}}, "id": "edge-0.87556121356007721714968654591", "startPoint": {"x": 880.0815636750158, "y": 298.3, "anchorIndex": 2}, "endPoint": {"x": 1003.5564870774778, "y": 372.6, "anchorIndex": 3}, "curveOffset": [-20, 20], "curvePosition": [0.5, 0.5], "sourceAnchor": 2, "targetAnchor": 3, "sourceAnchorID": "Output21714968566510", "depth": 0}]
unconnected_inputs = [{"source": None, "sourceAnchor": None, "target": "Gpt.py1714968515288", "anchorIndex": 0, "name": "Input1", "IsLabel": True, "Kind": "String", "Num": None, "Context": "", "Boolean": False}, {"source": None, "sourceAnchor": None, "target": "Add.py1714968620863", "anchorIndex": 0, "name": "Input1", "IsLabel": True, "Kind": "Num", "Num": 1, "Context": "", "Boolean": False}, {"source": None, "sourceAnchor": None, "target": "Add.py1714968620863", "anchorIndex": 1, "name": "Input2", "IsLabel": True, "Kind": "Num", "Num": 0, "Context": "", "Boolean": False}, {"source": None, "sourceAnchor": None, "target": "Add.py1714968634039", "anchorIndex": 0, "name": "Input1", "IsLabel": True, "Kind": "Num", "Num": 0, "Context": "", "Boolean": False}, {"source": None, "sourceAnchor": None, "target": "Add.py1714968634039", "anchorIndex": 1, "name": "Input2", "IsLabel": True, "Kind": "Num", "Num": 0, "Context": "", "Boolean": False}]
unconnected_outputs = [{"source": "Gpt.py1714968515288", "anchorIndex": 2, "target": None, "targetAnchor": None, "name": "Output2"}, {"source": "Add.py1714968620863", "anchorIndex": 2, "target": None, "targetAnchor": None, "name": "OutPut1"}, {"source": "Add.py1714968634039", "anchorIndex": 2, "target": None, "targetAnchor": None, "name": "OutPut1"}]
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