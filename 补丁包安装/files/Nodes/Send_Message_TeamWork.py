import json
import re
import os
from openpyxl import load_workbook, Workbook
import requests

# Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 5

# Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': None, 'Id': f'Output{i + 1}', 'name': 'WebOutput', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': None, 'Id': f'Input{i + 1}', 'Isnecessary': True, 'name': 'WebInput', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]

NodeKind = 'Normal_TeamWork'

InputIsAdd = False
OutputIsAdd = False
Label = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个TeamWork消息发送节点，用于在TeamWork系统中实现不同代理之间的HTTP消息通信功能。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n通过HTTP POST请求将消息发送到指定服务器端点，构建包含接收者、消息内容、限制标志和发送者信息的JSON数据包，并处理请求响应或异常情况。\\n\\n参数\\n```yaml\\ninputs:\\n  - name: port\\n    type: string\\n    required: true\\n    description: 消息发送的目标服务器端口\\n  - name: AgentName\\n    type: string\\n    required: true\\n    description: 发送消息的代理名称\\n  - name: To\\n    type: string\\n    required: true\\n    description: 消息的接收者\\n  - name: Message\\n    type: string\\n    required: true\\n    description: 要发送的消息内容\\n  - name: IsLimite\\n    type: boolean\\n    required: true\\n    description: 是否有发送限制的标志位\\noutputs:\\n  - name: Result\\n    type: string\\n    description: 消息发送的结果，包含成功状态或错误信息\\n```\\n\\n运行逻辑\\n- 从输入节点获取5个参数：服务器端口、代理名称、接收者、消息内容和限制标志\\n- 使用端口号构建完整的HTTP请求URL（http://{port}/send_message）\\n- 设置HTTP请求头为JSON格式（Content-Type: application/json）\\n- 将输入参数组织成JSON数据包，包含to（接收者）、content（消息内容）、is_limite（限制标志）和From（发送者）字段\\n- 通过requests.post方法发送HTTP POST请求到目标服务器\\n- 调用response.raise_for_status()检查HTTP响应状态\\n- 如果请求成功，从响应JSON中提取status字段作为结果，若无status字段则返回默认成功消息\\n- 如果请求过程中发生RequestException异常，捕获异常并格式化错误信息\\n- 将最终结果（成功状态或错误信息）赋值给输出节点Result的Context字段\\n- 返回包含处理结果的Outputs数组'

# Assign properties to Inputs and Outputs
Inputs[0]['Kind'] = 'String'  # File name
Inputs[0]['name'] = 'port'
Inputs[2]['Kind'] = 'String'  # File path
Inputs[2]['name'] = 'To'
Inputs[3]['Kind'] = 'String'  # Content
Inputs[3]['name'] = 'Message'
Inputs[4]['Kind'] = 'Boolean'  # IsLimite
Inputs[4]['name'] = 'IsLimite'
Inputs[1]['Kind'] = 'String'  # AgentName
Inputs[1]['name'] = 'AgentName'

Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Result'
# run_node部分
def run_node(node):
    port = node['Inputs'][0]['Context']
    to = node['Inputs'][2]['Context']
    message = node['Inputs'][3]['Context']
    is_limite = node['Inputs'][4]['Boolean']
    agent_name = node['Inputs'][1]['Context']

    try:
        # 构建请求URL和数据
        url = f"http://{port}/send_message"
        headers = {'Content-Type': 'application/json'}
        data = {
            'to': to,
            'content': message,
            'is_limite': is_limite,
            'From': agent_name

        }
        
        # 发送POST请求
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()
        
        result = response.json().get('status', 'Message sent successfully')
        Outputs[0]['Context'] = result
        
    except requests.RequestException as e:
        Outputs[0]['Context'] = f"Error: {str(e)}"
    
    return Outputs
