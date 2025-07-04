import json
import http.client
import requests
#**Define the number of outputs and inputs
OutPutNum = 3
InPutNum = 2
#**Define the number of outputs and inputs

#创建一个数组用于储存输出的值

#**Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Kind': None,'Boolean':False, 'Id': f'Output{i + 1}', 'Context': None,'name':f'OutPut{i + 1}','Link':0,'Description':''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True,'name':f'Input{i + 1}','Link':0,'IsLabel':False} for i in range(InPutNum)]
#**Initialize Outputs and Inputs arrays and assign names directly
NodeKind = 'passivityTrigger'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个消息触发器节点，用于从TeamWork系统获取指定代理的未回复消息，实现自动化消息监控和处理。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n通过HTTP POST请求向指定的Flask服务器发送代理名称，获取该代理的所有未回复消息，并将每条消息的发送者、内容和历史记录分别输出到三个端口。支持批量消息处理，对每条消息生成一组完整的输出结果。\\n\\n参数\\n```yaml\\ninputs:\\n  - name: HostPort\\n    type: string\\n    required: true\\n    description: Flask应用的主机地址和端口号\\n  - name: AgentName\\n    type: string\\n    required: true\\n    description: 需要获取消息的代理名称\\noutputs:\\n  - name: From\\n    type: string\\n    description: 消息的发送者信息\\n  - name: NewMessage\\n    type: string\\n    description: 新接收到的消息内容\\n  - name: HistoryMessage\\n    type: string\\n    description: 相关的历史消息记录\\n```\\n\\n运行逻辑\\n- 验证输入参数HostPort和AgentName是否存在，缺失则输出错误信息并返回None\\n- 构建API请求URL：\\\"http://{HostPort}/get_messages\\\"\\n- 设置HTTP请求头为JSON格式，准备包含agent_name的请求数据\\n- 向目标URL发送POST请求，传递代理名称参数\\n- 接收服务器返回的JSON响应，包含指定代理的所有未回复消息\\n- 检查返回的消息列表是否为空，为空则输出提示信息并返回None\\n- 对每条消息进行处理：创建输出数组的深拷贝，避免数据覆盖\\n- 从每条消息中提取From（发送者）、context（消息内容）、History（历史记录）三个字段\\n- 将提取的数据分别赋值给三个输出端口：From、NewMessage、HistoryMessage\\n- 输出调试信息显示当前处理的消息详情\\n- 将每组输出结果添加到返回数组中，实现多消息批量输出\\n- 异常处理包括网络请求错误和JSON解析错误，出错时输出相应错误信息并返回None'


#**Assign properties to Inputs

for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'
#**Assign properties to Inputs
Inputs[0]['name'] = 'HostPort'
Inputs[0]['Isnecessary'] = True
Inputs[1]['name'] = 'AgentName'
Inputs[1]['Isnecessary'] = True
Outputs[0]['name'] = 'From'
Outputs[1]['name'] = 'NewMessage'
Outputs[2]['name'] = 'HistoryMessage'

#**Function definition#**Function definition
def run_node(node):
    Array = []
    
    for output in Outputs:
        output['Context'] = None
    
    # 从输入中获取 HostPort 和 AgentName
    host_port = node['Inputs'][0]['Context']
    agent_name = node['Inputs'][1]['Context']
    
    if not host_port or not agent_name:
        print("Error: HostPort and AgentName are required inputs.")
        return None

    # 构建完整的 URL
    url = f"http://{host_port}/get_messages"  # 添加/api前缀
    
    try:
        # 使用POST方法，发送JSON格式数据
        headers = {'Content-Type': 'application/json'}
        data = {'agent_name': agent_name}
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()
        
        messages = response.json()
        
        if messages:  # 如果有消息
            for message in messages:
                # Ensure Outputs is structured correctly
                if not isinstance(Outputs, list) or len(Outputs) < 3:
                    print("Error: Outputs is not structured correctly.")
                    return None
                
                output_copy = [output.copy() for output in Outputs]  # Ensure deep copy if Outputs contains mutable objects
                
                # Assign values with checks
                output_copy[0]['Context'] = message.get('From', '')
                output_copy[1]['Context'] = message.get('context', '')
                output_copy[2]['Context'] = message.get('History', '')
                
                # Debug prints
                print("Debug Message From:", message.get('From', ''))
                print("Debug Message Context:", message.get('context', ''))
                print("Debug Message History:", message.get('History', ''))
                
                Array.append(output_copy)
            
            return Array

        print("No messages found for the specified agent.")
        return None

        
    except requests.RequestException as e:
        print(f"Network error: {e}")
        return None
    except json.JSONDecodeError:
        print(f"Failed to decode JSON from response: {response.text}")
        return None
