import json
import re
OutPutNum = 2
InPutNum = 6
Outputs = [{'Num': None, 'Kind': 'Num', 'Id': 'Add.py1714790910902_2', 'Context': None,'Boolean': False,'name': 'OutPut1','Link':0,'Description':'answer'}, {'Num': None, 'Kind': 'Num', 'Id': 'Add.py1714790919960_2', 'Context': None,'Boolean': False,'name': 'OutPut1','Link':0,'Description':'answer'}]
Inputs = [{'Num': 1, 'Context': '', 'Boolean': False, 'Kind': 'Num', 'Id': 'Input1', 'IsLabel': True, 'name': 'Input1'}, {'Num': 1, 'Context': '', 'Boolean': False, 'Kind': 'Num', 'Id': 'Input2', 'IsLabel': True, 'name': 'Input21'}, {'Num': 1, 'Context': '', 'Boolean': False, 'Kind': 'Num', 'Id': 'Input3', 'IsLabel': True, 'name': 'Input1'}, {'Num': 1, 'Context': '', 'Boolean': False, 'Kind': 'Num', 'Id': 'Input4', 'IsLabel': True, 'name': 'Input2'}, {'Num': 3, 'Context': '', 'Boolean': False, 'Kind': 'Num', 'Id': 'Input5', 'IsLabel': True, 'name': 'Input1'}, {'Num': 1, 'Context': '', 'Boolean': False, 'Kind': 'Num', 'Id': 'Input6', 'IsLabel': True, 'name': 'Input2'}]
NodeKind = 'Normal'
nodes = [{"id": "Add.py1714790888425", "name": "Add.py", "label": "Add.py0", "hash": "b674dbca8e7bfc6fa675e78f8e1e840c7e26a7d1bf2ecdf24fd6eec2bcccd457", "x": 182, "y": 258, "TriggerLink": 0, "IsHovor": False, "IsBlock": False, "IsRunning": False, "isFinish": False, "IsError": False, "IsTrigger": False, "ErrorContext": "", "prompt": "", "ExprotPrompt": "\nPlease ensure the output is in JSON format\n{\n\"Output11\":\"undefined\"(you need output type:Num)\n}\n", "ExprotAfterPrompt": "Please ensure the output is in JSON format\n{\n\"Output11\":\"undefined\"(you need output type:Num)\n}\n", "anchorPoints": [[0.029820147236976985, 0.6], [0.029820147236976985, 0.8], [0.9652098282235269, 0.6], [0.049700245394961644, 0.1]], "Inputs": [{"Context": None, "Id": "Input1", "IsLabel": True, "Isnecessary": True, "Kind": "Num", "Link": 0, "Num": 1, "name": "Input1", "isConnected": False}, {"Context": None, "Id": "Input2", "IsLabel": True, "Isnecessary": True, "Kind": "Num", "Link": 0, "Num": 1, "name": "Input21", "isConnected": False}], "Lable": [{"Id": "Label1", "Kind": "None"}], "NodeKind": "Normal", "Outputs": [{"Context": None, "Id": "Output11", "Kind": "Num", "Link": 2, "Num": 2, "name": "OutPut1"}], "type": "fileNode", "style": {"hover": {"fill": "lightgreen"}, "active": {"stroke": "#ff0000", "lineWidth": 100}}, "draggable": False, "height": 40, "width": 201.20624999999998, "depth": 0, "inputStatus": [False, False], "firstRun": False}, {"id": "IfNode.py1714790890742", "name": "IfNode.py", "label": "IfNode.py1", "hash": "2e72f423b86ccef76144b09929ade4000e18e10d3146be24f54f6922809c0981", "x": 681, "y": 305, "TriggerLink": 0, "IsHovor": False, "IsBlock": False, "IsRunning": False, "isFinish": False, "IsError": False, "IsTrigger": False, "ErrorContext": "", "prompt": "", "ExprotPrompt": "\nPlease ensure the output is in JSON format\n{\n\"Output1\":\"\"(you need output type:)\n}\n", "ExprotAfterPrompt": "Please ensure the output is in JSON format\n{\n\"Output1\":\"\"(you need output type:)\n}\n", "anchorPoints": [[0.03622667141512794, 0.6], [0.9577355500156841, 0.6], [0.9577355500156841, 0.8], [0.0603777856918799, 0.1]], "Inputs": [{"Num": 2, "Kind": "Num", "Id": "Input11714790901529", "Context": None, "Isnecessary": False, "name": "Input1", "Link": 2, "IsLabel": False, "isConnected": False}], "Lable": [{"Id": "Label1", "Kind": "None"}], "NodeKind": "IfNode", "Outputs": [{"Boolean": True, "Context": "", "Description": "", "Id": "Output1", "Kind": "Trigger", "Link": 2, "Num": 0, "name": "OutPut1", "selectBox1": "Input1", "selectBox2": ">", "selectBox3": "1", "selectKind": "Num", "selectNum": 0}, {"Num": 0, "Kind": "Trigger", "Id": "Output21714790959321", "Context": "", "Boolean": False, "Isnecessary": True, "name": "Output2", "Link": 2, "IsLabel": False, "selectBox1": "Input1", "selectBox2": "<", "selectBox3": "1", "selectKind": "Num", "selectNum": 0}], "type": "fileNode", "style": {"hover": {"fill": "lightgreen"}, "active": {"stroke": "#ff0000", "lineWidth": 100}}, "draggable": False, "height": 40, "width": 165.623828125, "depth": 0, "inputStatus": [True], "firstRun": True}, {"id": "Add.py1714790910902", "name": "Add.py", "label": "Add.py2", "hash": "b674dbca8e7bfc6fa675e78f8e1e840c7e26a7d1bf2ecdf24fd6eec2bcccd457", "x": 1131, "y": 185, "TriggerLink": 2, "IsHovor": False, "IsBlock": False, "IsRunning": False, "isFinish": False, "IsError": False, "IsTrigger": False, "ErrorContext": "", "prompt": "", "ExprotPrompt": "\nPlease ensure the output is in JSON format\n{\n\"Output11\":\"undefined\"(you need output type:Num)\n}\n", "ExprotAfterPrompt": "Please ensure the output is in JSON format\n{\n\"Output11\":\"undefined\"(you need output type:Num)\n}\n", "anchorPoints": [[0.033892246486658235, 0.6], [0.033892246486658235, 0.8], [0.9604590457655654, 0.6], [0.05648707747776373, 0.1]], "Inputs": [{"Context": None, "Id": "Input1", "IsLabel": True, "Isnecessary": True, "Kind": "Num", "Link": 0, "Num": 1, "name": "Input1", "isConnected": False}, {"Context": None, "Id": "Input2", "IsLabel": True, "Isnecessary": True, "Kind": "Num", "Link": 0, "Num": 1, "name": "Input2", "isConnected": False}], "Lable": [{"Id": "Label1", "Kind": "None"}], "NodeKind": "Normal", "Outputs": [{"Context": "", "Id": "Output11", "Kind": "Num", "Link": 0, "Num": 0, "name": "OutPut1"}], "type": "fileNode", "style": {"hover": {"fill": "lightgreen"}, "active": {"stroke": "#ff0000", "lineWidth": 100}}, "draggable": False, "height": 40, "width": 177.031640625, "depth": 0, "inputStatus": [False, False, None, True], "firstRun": True}, {"id": "Add.py1714790919960", "name": "Add.py", "label": "Add.py3", "hash": "b674dbca8e7bfc6fa675e78f8e1e840c7e26a7d1bf2ecdf24fd6eec2bcccd457", "x": 1173, "IsHovor": False, "y": 377, "TriggerLink": 2, "IsBlock": False, "IsRunning": False, "IsError": False, "isFinish": False, "IsTrigger": True, "ErrorContext": "", "prompt": "", "ExprotPrompt": "\nPlease ensure the output is in JSON format\n{\n\"Output11\":\"undefined\"(you need output type:Num)\n}\n", "ExprotAfterPrompt": "Please ensure the output is in JSON format\n{\n\"Output11\":\"undefined\"(you need output type:Num)\n}\n", "anchorPoints": [[0.033892246486658235, 0.6], [0.033892246486658235, 0.8], [0.9604590457655654, 0.6], [0.05648707747776373, 0.1]], "Inputs": [{"Context": None, "Id": "Input1", "IsLabel": True, "Isnecessary": True, "Kind": "Num", "Link": 0, "Num": 3, "name": "Input1", "isConnected": False}, {"Context": None, "Id": "Input2", "IsLabel": True, "Isnecessary": True, "Kind": "Num", "Link": 0, "Num": 1, "name": "Input2", "isConnected": False}], "Lable": [{"Id": "Label1", "Kind": "None"}], "NodeKind": "Normal", "Outputs": [{"Context": "", "Id": "Output11", "Kind": "Num", "Link": 0, "Num": 0, "name": "OutPut1"}], "type": "fileNode", "style": {"hover": {"fill": "lightgreen"}, "active": {"stroke": "#ff0000", "lineWidth": 100}}, "draggable": False, "height": 40, "width": 177.031640625, "depth": 0, "inputStatus": [False, False], "firstRun": True}]
edges = [{"source": "Add.py1714790888425", "target": "IfNode.py1714790890742", "type": "line-dash", "style": {"lineWidth": 3, "stroke": "#000", "endArrow": {"path": "M 0,0 L 12,6 L 12,-6 Z", "fill": "#5c95ff", "d": -10}, "active": {"stroke": "rgb(95, 149, 255)", "lineWidth": 1}, "selected": {"stroke": "rgb(95, 149, 255)", "lineWidth": 2, "shadowColor": "rgb(95, 149, 255)", "shadowBlur": 10, "text-shape": {"fontWeight": 500}}, "highlight": {"stroke": "rgb(95, 149, 255)", "lineWidth": 2, "text-shape": {"fontWeight": 500}}, "inactive": {"stroke": "rgb(234, 234, 234)", "lineWidth": 1}, "disable": {"stroke": "rgb(245, 245, 245)", "lineWidth": 1}}, "id": "edge-0.34471578585656571714790905669", "startPoint": {"x": 376.6714598282235, "y": 318.1, "anchorIndex": 2}, "endPoint": {"x": 686.5362266714151, "y": 365.1, "anchorIndex": 0}, "curveOffset": [-20, 20], "curvePosition": [0.5, 0.5], "sourceAnchor": 2, "targetAnchor": 0, "sourceAnchorID": "Output11", "targetAnchorID": "Input11714790901529", "depth": 0}, {"source": "IfNode.py1714790890742", "target": "Add.py1714790910902", "type": "line-dash", "style": {"lineWidth": 3, "stroke": "#000", "endArrow": {"path": "M 0,0 L 12,6 L 12,-6 Z", "fill": "#5c95ff", "d": -10}, "active": {"stroke": "rgb(95, 149, 255)", "lineWidth": 1}, "selected": {"stroke": "rgb(95, 149, 255)", "lineWidth": 2, "shadowColor": "rgb(95, 149, 255)", "shadowBlur": 10, "text-shape": {"fontWeight": 500}}, "highlight": {"stroke": "rgb(95, 149, 255)", "lineWidth": 2, "text-shape": {"fontWeight": 500}}, "inactive": {"stroke": "rgb(234, 234, 234)", "lineWidth": 1}, "disable": {"stroke": "rgb(245, 245, 245)", "lineWidth": 1}}, "id": "edge-0.64514171208191141714790912238", "startPoint": {"x": 840.0815636750158, "y": 365.1, "anchorIndex": 1}, "endPoint": {"x": 1140.5564870774779, "y": 194.6, "anchorIndex": 3}, "curveOffset": [-20, 20], "curvePosition": [0.5, 0.5], "sourceAnchor": 1, "targetAnchor": 3, "sourceAnchorID": "Output1", "depth": 0}, {"source": "IfNode.py1714790890742", "target": "Add.py1714790919960", "type": "line-dash", "style": {"lineWidth": 3, "stroke": "#000", "endArrow": {"path": "M 0,0 L 12,6 L 12,-6 Z", "fill": "#5c95ff", "d": -10}, "active": {"stroke": "rgb(95, 149, 255)", "lineWidth": 1}, "selected": {"stroke": "rgb(95, 149, 255)", "lineWidth": 2, "shadowColor": "rgb(95, 149, 255)", "shadowBlur": 10, "text-shape": {"fontWeight": 500}}, "highlight": {"stroke": "rgb(95, 149, 255)", "lineWidth": 2, "text-shape": {"fontWeight": 500}}, "inactive": {"stroke": "rgb(234, 234, 234)", "lineWidth": 1}, "disable": {"stroke": "rgb(245, 245, 245)", "lineWidth": 1}}, "id": "edge-0.99033544836391751714790965110", "startPoint": {"x": 840.0815636750158, "y": 385.3, "anchorIndex": 2}, "endPoint": {"x": 1182.5564870774779, "y": 386.6, "anchorIndex": 3}, "curveOffset": [-20, 20], "curvePosition": [0.5, 0.5], "sourceAnchor": 2, "targetAnchor": 3, "sourceAnchorID": "Output21714790959321", "depth": 0}]
unconnected_inputs = [{"source": None, "sourceAnchor": None, "target": "Add.py1714790888425", "anchorIndex": 0, "name": "Input1", "IsLabel": True, "Kind": "Num", "Num": 1, "Context": "", "Boolean": False}, {"source": None, "sourceAnchor": None, "target": "Add.py1714790888425", "anchorIndex": 1, "name": "Input21", "IsLabel": True, "Kind": "Num", "Num": 1, "Context": "", "Boolean": False}, {"source": None, "sourceAnchor": None, "target": "Add.py1714790910902", "anchorIndex": 0, "name": "Input1", "IsLabel": True, "Kind": "Num", "Num": 1, "Context": "", "Boolean": False}, {"source": None, "sourceAnchor": None, "target": "Add.py1714790910902", "anchorIndex": 1, "name": "Input2", "IsLabel": True, "Kind": "Num", "Num": 1, "Context": "", "Boolean": False}, {"source": None, "sourceAnchor": None, "target": "Add.py1714790919960", "anchorIndex": 0, "name": "Input1", "IsLabel": True, "Kind": "Num", "Num": 3, "Context": "", "Boolean": False}, {"source": None, "sourceAnchor": None, "target": "Add.py1714790919960", "anchorIndex": 1, "name": "Input2", "IsLabel": True, "Kind": "Num", "Num": 1, "Context": "", "Boolean": False}]
unconnected_outputs = [{"source": "Add.py1714790910902", "anchorIndex": 2, "target": None, "targetAnchor": None, "name": "OutPut1"}, {"source": "Add.py1714790919960", "anchorIndex": 2, "target": None, "targetAnchor": None, "name": "OutPut1"}]
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
                output['Num'] = data[i]['Num']
                output['Context'] = data[i]['Context']
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
                    if (targetNode and len(targetNode['Inputs']) > edge['targetAnchor']) or (targetNode and len(targetNode['Input'])+len(targetNode['Outputs']) == edge['targetAnchor'] and targetNode['NodeKind'] == 'IfNode'):
                        if(targetNode and len(targetNode['Inputs']) > edge['targetAnchor']):
                            targetNode['Inputs'][edge['targetAnchor']]['Num'] = data[edge['sourceAnchor'] - len(nodez['Inputs'])]['Num']
                            targetNode['Inputs'][edge['targetAnchor']]['Context'] = data[edge['sourceAnchor'] - len(nodez['Inputs'])]['Context']
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
            print(f"Function {node_function_name} not found")
def Add_py1714790888425_run_node(node):
   #**Define the number of outputs and inputs
   OutPutNum_node = 1
   InPutNum_node = 2
   #**Define the number of outputs and inputs
   #**Initialize Outputs_node and Inputs_node arrays and assign names directly
   Outputs_node = [{'Num': None, 'Kind': None, 'Id': f'Output1{i + 1}', 'Context': None,'name':f'OutPut{i + 1}','Link':0} for i in range(OutPutNum_node)]
   Inputs_node = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True,'name':f'Input{i + 1}','Link':0,'IsLabel':False} for i in range(InPutNum_node)]
   #**Initialize Outputs_node and Inputs_node arrays and assign names directly
   NodeKind = 'Normal'
   Lable = [{'Id': 'Label1', 'Kind': 'None'}]
   #**Assign properties to Inputs_node
   for output in Outputs_node:
       output['Kind'] = 'Num'
   for input in Inputs_node:
       input['Kind'] = 'Num'
   #**Assign properties to Inputs_node
   #**Function definition
   def run_nodes(node):
       total = 0
       for i in range(len(node['Inputs'])):
           total += node['Inputs'][i]['Num']
       Outputs_node[0]['Num'] = total
       print(total)
       return Outputs_node
   #**Function definition
   return run_nodes(node)
def IfNode_py1714790890742_run_node(node):
   #**Define the number of outputs and inputs
   OutPutNum_node = 1
   InPutNum_node = 0
   #**Define the number of outputs and inputs
   #**Initialize Outputs_node and Inputs_node arrays and assign names directly
   Outputs_node = [{'Num': None, 'Kind': None,'Boolean':False, 'Id': f'Output{i + 1}', 'Context': None,'name':f'OutPut{i + 1}','Link':0,'Description':''} for i in range(OutPutNum_node)]
   Inputs_node = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True,'name':f'Input{i + 1}','Link':0,'IsLabel':False} for i in range(InPutNum_node)]
   #**Initialize Outputs_node and Inputs_node arrays and assign names directly
   NodeKind = 'IfNode'
   Lable = [{'Id': 'Label1', 'Kind': 'None'}]
   #**Assign properties to Inputs_node
   for output in Outputs_node:
       output['Kind'] = 'Trigger'
   for input in Inputs_node:
       input['Kind'] = 'String'
   #**Assign properties to Inputs_node
   #**Function definition
   def run_nodes(node):
       Outputs_node.clear()
       for i in range(len(node['Outputs'])):
           Outputs_node.append(node['Outputs'][i])
           Outputs_node[i]['Boolean'] = False
       #print('Out阿松大',Outputs_node)
       for i, output in enumerate(Outputs_node):
           if output.get('selectKind') == 'String' and output.get('selectNum') is not None:
               input_value = node['Inputs'][output['selectNum']]['Context']
               # 检查是否不包含 selectBox3 的值
               if output['selectBox2'] == 'exclude' and output['selectBox3'] is not None:
                   if output['selectBox3'] not in input_value:
                       # 执行当 input_value 不包含 selectBox3 的值时的操作
                       print("Does not include the specified value.")
                       output['Boolean'] = True
               # 检查 input_value 是否为空
               if output['selectBox2'] == 'empty' and output['selectBox3'] is not None:
                   if input_value == '':
                       # 执行当 input_value 为空的操作
                       print("Value is empty.")
                       output['Boolean'] = True
               # 检查 input_value 是否不为空
               if output['selectBox2'] == 'not empty' and output['selectBox3'] is not None:
                   if input_value != '':
                       # 执行当 input_value 不为空的操作
                       print("Value is not empty.")
                       output['Boolean'] = True
               # 检查是否包含 selectBox3 的值
               print('测试',output['selectBox2'],output['selectBox3'],input_value)
               if output['selectBox2'] == 'include' and output['selectBox3'] is not None:
                   print('input_value',output['selectBox3'],input_value)
                   if output['selectBox3'] in input_value:
                       # 执行当 input_value 包含 selectBox3 的值时的操作
                       print("Includes the specified value.")
                       output['Boolean'] = True
                   #检查是否包含
           if output.get('selectKind') == 'Num' and output.get('selectNum') is not None:
               input_value = node['Inputs'][output['selectNum']]['Num']
               if output['selectBox2'] == '>':
                   if input_value > int(output['selectBox3']):
                       output['Boolean'] = True
               if output['selectBox2'] == '<':
                   if input_value < int(output['selectBox3']):
                       output['Boolean'] = True
               if output['selectBox2'] == '==':
                   if input_value == int(output['selectBox3']):
                       output['Boolean'] = True
               if output['selectBox2'] == '!=':
                   if input_value != int(output['selectBox3']):
                       output['Boolean'] = True
               if output['selectBox2'] == '>=':
                   if input_value >= int(output['selectBox3']):
                       output['Boolean'] = True
               if output['selectBox2'] == '<=':
                   if input_value <= int(output['selectBox3']):
                       output['Boolean'] = True
           #print('input_argsdas1大',output.get('Kind'),output.get('selectNum'),input_args)
           if output.get('selectKind') == 'Boolean' and output.get('selectNum') is not None:
               #print('啊实打实VS地方',input_args[output['selectNum']],output['selectBox2'])
               if output['selectBox2'] == 'true':
                   if node['Inputs'][output['selectNum']]['Boolean'] == True:
                       output['Boolean'] = True
               if output['selectBox2'] == 'False' :
                   if node['Inputs'][output['selectNum']]['Boolean']  == False:
                       output['Boolean'] = True
           output['Kind'] = 'Boolean'
       #print(Outputs_node,input_args)
       return Outputs_node
   #**Function definition
   return run_nodes(node)
def Add_py1714790910902_run_node(node):
   #**Define the number of outputs and inputs
   OutPutNum_node = 1
   InPutNum_node = 2
   #**Define the number of outputs and inputs
   #**Initialize Outputs_node and Inputs_node arrays and assign names directly
   Outputs_node = [{'Num': None, 'Kind': None, 'Id': f'Output1{i + 1}', 'Context': None,'name':f'OutPut{i + 1}','Link':0} for i in range(OutPutNum_node)]
   Inputs_node = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True,'name':f'Input{i + 1}','Link':0,'IsLabel':False} for i in range(InPutNum_node)]
   #**Initialize Outputs_node and Inputs_node arrays and assign names directly
   NodeKind = 'Normal'
   Lable = [{'Id': 'Label1', 'Kind': 'None'}]
   #**Assign properties to Inputs_node
   for output in Outputs_node:
       output['Kind'] = 'Num'
   for input in Inputs_node:
       input['Kind'] = 'Num'
   #**Assign properties to Inputs_node
   #**Function definition
   def run_nodes(node):
       total = 0
       for i in range(len(node['Inputs'])):
           total += node['Inputs'][i]['Num']
       Outputs_node[0]['Num'] = total
       print(total)
       return Outputs_node
   #**Function definition
   return run_nodes(node)
def Add_py1714790919960_run_node(node):
   #**Define the number of outputs and inputs
   OutPutNum_node = 1
   InPutNum_node = 2
   #**Define the number of outputs and inputs
   #**Initialize Outputs_node and Inputs_node arrays and assign names directly
   Outputs_node = [{'Num': None, 'Kind': None, 'Id': f'Output1{i + 1}', 'Context': None,'name':f'OutPut{i + 1}','Link':0} for i in range(OutPutNum_node)]
   Inputs_node = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True,'name':f'Input{i + 1}','Link':0,'IsLabel':False} for i in range(InPutNum_node)]
   #**Initialize Outputs_node and Inputs_node arrays and assign names directly
   NodeKind = 'Normal'
   Lable = [{'Id': 'Label1', 'Kind': 'None'}]
   #**Assign properties to Inputs_node
   for output in Outputs_node:
       output['Kind'] = 'Num'
   for input in Inputs_node:
       input['Kind'] = 'Num'
   #**Assign properties to Inputs_node
   #**Function definition
   def run_nodes(node):
       total = 0
       for i in range(len(node['Inputs'])):
           total += node['Inputs'][i]['Num']
       Outputs_node[0]['Num'] = total
       print(total)
       return Outputs_node
   #**Function definition
   return run_nodes(node)
