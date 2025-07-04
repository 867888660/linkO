import http.client
import json
import re
OutPutNum = 1
InPutNum = 0
Outputs = [{'Num': None, 'Kind': 'String', 'Id': 'Gpt.py1714811858469_1', 'Context': None,'Boolean': False,'name': 'OutPut1','Link':0,'Description':'answer'}]
Inputs = []
NodeKind = 'Normal'
nodes = [{"id": "Gpt.py1714811857632", "name": "Gpt.py", "label": "Gpt.py0", "hash": "845dd5010b5fcbfa596c33dfc641cd0320d5519cfa4769ab01d1207ed4066a7a", "x": 525, "y": 169, "TriggerLink": 0, "IsHovor": False, "IsBlock": True, "IsRunning": False, "isFinish": True, "IsError": False, "IsTrigger": False, "ErrorContext": "", "prompt": "\u4f60\u76f8\u4fe1\u81ea\u7531\u610f\u5fd7\u5417\uff1f", "ExprotPrompt": "\u4f60\u76f8\u4fe1\u81ea\u7531\u610f\u5fd7\u5417\uff1f\nPlease ensure the output is in JSON format\n{\n\"Output1\":\"answer\"(you need output type:String)\n}\n", "ExprotAfterPrompt": "Please ensure the output is in JSON format\n{\n\"Output1\":\"answer\"(you need output type:String)\n}\n", "anchorPoints": [[0.9576474480933079, 0.75], [0.06050364558098862, 0.125]], "Inputs": [], "Lable": [{"Id": "Label1", "Kind": "None"}], "NodeKind": "LLm", "Outputs": [{"Boolean": False, "Context": "\u6211\u662f\u4e00\u4e2aAI\u52a9\u624b\uff0c\u6ca1\u6709\u81ea\u7531\u610f\u5fd7\u3002", "Description": "answer", "Id": "Output1", "Kind": "String", "Link": 1, "Num": 0, "name": "OutPut1"}], "type": "fileNode", "style": {"hover": {"fill": "lightgreen"}, "active": {"stroke": "#ff0000", "lineWidth": 100}}, "draggable": False, "height": 20, "width": 165.279296875, "depth": 0, "inputStatus": [], "firstRun": False}, {"id": "Gpt.py1714811858469", "name": "Gpt.py", "label": "Gpt.py1", "hash": "845dd5010b5fcbfa596c33dfc641cd0320d5519cfa4769ab01d1207ed4066a7a", "x": 803, "y": 206, "TriggerLink": 0, "IsHovor": False, "IsBlock": True, "IsRunning": False, "isFinish": True, "IsError": False, "IsTrigger": False, "ErrorContext": "\u8282\u70b9\u8fd0\u884c\u6709Bug", "prompt": "{{Input1}}\u53cd\u9a73\u6211", "ExprotPrompt": "\u6211\u662f\u4e00\u4e2aAI\u52a9\u624b\uff0c\u6ca1\u6709\u81ea\u7531\u610f\u5fd7\u3002\u53cd\u9a73\u6211\nPlease ensure the output is in JSON format\n{\n\"Output1\":\"answer\"(you need output type:String)\n}\n", "ExprotAfterPrompt": "Please ensure the output is in JSON format\n{\n\"Output1\":\"answer\"(you need output type:String)\n}\n", "anchorPoints": [[0.036302187348593175, 0.75], [0.9576474480933079, 0.75], [0.06050364558098862, 0.125]], "Inputs": [{"Num": 0, "Kind": "String", "Id": "Input11714811860170", "Context": "\u6211\u662f\u4e00\u4e2aAI\u52a9\u624b\uff0c\u6ca1\u6709\u81ea\u7531\u610f\u5fd7\u3002", "Isnecessary": False, "name": "Input1", "Link": 1, "IsLabel": False, "isConnected": False, "Boolean": False}], "Lable": [{"Id": "Label1", "Kind": "None"}], "NodeKind": "LLm", "Outputs": [{"Boolean": False, "Context": "", "Description": "answer", "Id": "Output1", "Kind": "String", "Link": 0, "Num": 0, "name": "OutPut1"}], "type": "fileNode", "style": {"hover": {"fill": "lightgreen"}, "active": {"stroke": "#ff0000", "lineWidth": 100}}, "draggable": False, "height": 20, "width": 165.279296875, "depth": 0, "inputStatus": [True], "firstRun": True}]
edges = [{"source": "Gpt.py1714811857632", "target": "Gpt.py1714811858469", "type": "line-dash", "style": {"active": {"stroke": "rgb(95, 149, 255)", "lineWidth": 1}, "selected": {"stroke": "rgb(95, 149, 255)", "lineWidth": 2, "shadowColor": "rgb(95, 149, 255)", "shadowBlur": 10, "text-shape": {"fontWeight": 500}}, "highlight": {"stroke": "rgb(95, 149, 255)", "lineWidth": 2, "text-shape": {"fontWeight": 500}}, "inactive": {"stroke": "rgb(234, 234, 234)", "lineWidth": 1}, "disable": {"stroke": "rgb(245, 245, 245)", "lineWidth": 1}, "lineWidth": 3, "stroke": "#000", "endArrow": {"path": "M 0,0 L 12,6 L 12,-6 Z", "fill": "#5c95ff", "d": -10}}, "id": "edge-0.43942577949616711714811861163", "startPoint": {"x": 683.7369443230933, "y": 229.25, "anchorIndex": 0}, "endPoint": {"x": 808.5363021873486, "y": 266.25, "anchorIndex": 0}, "curveOffset": [-20, 20], "curvePosition": [0.5, 0.5], "sourceAnchor": 0, "targetAnchor": 0, "sourceAnchorID": "Output1", "targetAnchorID": "Input11714811860170", "depth": 0}]
unconnected_inputs = []
unconnected_outputs = [{"source": "Gpt.py1714811858469", "anchorIndex": 1, "target": None, "targetAnchor": None, "name": "OutPut1"}]
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
def Gpt_py1714811857632_run_node(node):
   #**Define the number of outputs and inputs
   OutPutNum_node = 1
   InPutNum_node = 0
   #**Define the number of outputs and inputs
   #**Initialize Outputs_node and Inputs_node arrays and assign names directly
   Outputs_node = [{'Num': None, 'Kind': None,'Boolean':False, 'Id': f'Output{i + 1}', 'Context': None,'name':f'OutPut{i + 1}','Link':0,'Description':'answer'} for i in range(OutPutNum_node)]
   Inputs_node = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True,'name':f'Input{i + 1}','Link':0,'IsLabel':False} for i in range(InPutNum_node)]
   #**Initialize Outputs_node and Inputs_node arrays and assign names directly
   NodeKind = 'LLm'
   Lable = [{'Id': 'Label1', 'Kind': 'None'}]
   #**Assign properties to Inputs_node
   for output in Outputs_node:
       output['Kind'] = 'String'
   for input in Inputs_node:
       input['Kind'] = 'String'
   #**Assign properties to Inputs_node
   #**Function definition
   def run_nodes(node):
       Outputs_node.clear()
       for i in range(len(node['Outputs'])):
           Outputs_node.append(node['Outputs'][i])
       print(node['ExprotPrompt'])
       conn = http.client.HTTPSConnection("api.chatanywhere.com.cn")
       payload = json.dumps({
       "model": "gpt-3.5-turbo",
       "messages": [
           {
               "role": "user",
               "content": node['ExprotPrompt']
           }
       ]
       })
       headers = {
       'Authorization': 'Bearer sk-4rLJyJRai7olKeUbKM6NwQm2K7tGHF9ckq3xFBhjjlSDv9xy',
       'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
       'Content-Type': 'application/json'
       }
       conn.request("POST", "/v1/chat/completions", payload, headers)
       res = conn.getresponse()
       data = res.read()
       jsonObj = json.loads(data.decode("utf-8"))
       Temp = jsonObj['choices'][0]['message']['content']
       # Transform the Temp string into a JSON object, assuming it's structured as a dictionary.
       Temp_dict = json.loads(Temp)
       print('测试2',Temp_dict)
       index=-1
       # Perform the transformation directly here.
       for key, value in Temp_dict.items():
           index+=1
       # 确保Outputs_node[key]是一个字典
           print(index,value)
           # 首先判断是否为字符串
           if(isinstance(value,str)):
               if(Outputs_node[index]['Kind']=='String'):
                   Outputs_node[index]['Context']=value
               elif(Outputs_node[index]['Kind']=='Num'):
                   Outputs_node[index]['Num']=int(value)
               elif(Outputs_node[index]['Kind']=='Boolean'):
                   Outputs_node[index]['Boolean']=value
           print(json.dumps(Temp_dict, ensure_ascii=False))
       return Outputs_node
   #**Function definition
   return run_nodes(node)
def Gpt_py1714811858469_run_node(node):
   #**Define the number of outputs and inputs
   OutPutNum_node = 1
   InPutNum_node = 0
   #**Define the number of outputs and inputs
   #**Initialize Outputs_node and Inputs_node arrays and assign names directly
   Outputs_node = [{'Num': None, 'Kind': None,'Boolean':False, 'Id': f'Output{i + 1}', 'Context': None,'name':f'OutPut{i + 1}','Link':0,'Description':'answer'} for i in range(OutPutNum_node)]
   Inputs_node = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True,'name':f'Input{i + 1}','Link':0,'IsLabel':False} for i in range(InPutNum_node)]
   #**Initialize Outputs_node and Inputs_node arrays and assign names directly
   NodeKind = 'LLm'
   Lable = [{'Id': 'Label1', 'Kind': 'None'}]
   #**Assign properties to Inputs_node
   for output in Outputs_node:
       output['Kind'] = 'String'
   for input in Inputs_node:
       input['Kind'] = 'String'
   #**Assign properties to Inputs_node
   #**Function definition
   def run_nodes(node):
       Outputs_node.clear()
       for i in range(len(node['Outputs'])):
           Outputs_node.append(node['Outputs'][i])
       print(node['ExprotPrompt'])
       conn = http.client.HTTPSConnection("api.chatanywhere.com.cn")
       payload = json.dumps({
       "model": "gpt-3.5-turbo",
       "messages": [
           {
               "role": "user",
               "content": node['ExprotPrompt']
           }
       ]
       })
       headers = {
       'Authorization': 'Bearer sk-4rLJyJRai7olKeUbKM6NwQm2K7tGHF9ckq3xFBhjjlSDv9xy',
       'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
       'Content-Type': 'application/json'
       }
       conn.request("POST", "/v1/chat/completions", payload, headers)
       res = conn.getresponse()
       data = res.read()
       jsonObj = json.loads(data.decode("utf-8"))
       Temp = jsonObj['choices'][0]['message']['content']
       # Transform the Temp string into a JSON object, assuming it's structured as a dictionary.
       Temp_dict = json.loads(Temp)
       print('测试2',Temp_dict)
       index=-1
       # Perform the transformation directly here.
       for key, value in Temp_dict.items():
           index+=1
       # 确保Outputs_node[key]是一个字典
           print(index,value)
           # 首先判断是否为字符串
           if(isinstance(value,str)):
               if(Outputs_node[index]['Kind']=='String'):
                   Outputs_node[index]['Context']=value
               elif(Outputs_node[index]['Kind']=='Num'):
                   Outputs_node[index]['Num']=int(value)
               elif(Outputs_node[index]['Kind']=='Boolean'):
                   Outputs_node[index]['Boolean']=value
           print(json.dumps(Temp_dict, ensure_ascii=False))
       return Outputs_node
   #**Function definition
   return run_nodes(node)
