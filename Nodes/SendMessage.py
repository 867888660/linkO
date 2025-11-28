import json
import requests
#**Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 2
#**Define the number of outputs and inputs

#**Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Kind': None, 'Id': f'Output1{i + 1}', 'Context': None,'name':f'OutPut{i + 1}','Link':0} for i in range(OutPutNum)]
FunctionIntroduction='组件功能：这是一个HTTP消息发送节点，通过POST请求向本地服务器发送消息并返回响应结果。\\n\\n代码功能摘要：接收消息内容和接收者信息两个输入参数，将其组装成JSON格式数据，通过HTTP POST请求发送到本地服务器(http://localhost:5111/send)，处理响应并返回JSON格式的结果。\\n\\n参数：\\n```yaml\\ninputs:\\n  - name: Input1\\n    type: string\\n    required: true\\n    description: 要发送的消息内容\\n  - name: Input2\\n    type: string\\n    required: true\\n    description: 消息接收者信息\\noutputs:\\n  - name: OutPut1\\n    type: string\\n    description: HTTP请求的响应结果(JSON格式字符串)\\n```\\n\\n运行逻辑：\\n- 从输入参数中获取消息内容(Input1)和接收者信息(Input2)\\n- 将两个输入参数组装成JSON格式的请求数据：{\'message\': 消息内容, \'to_user\': 接收者信息}\\n- 向本地服务器http://localhost:5111/send发送HTTP POST请求\\n- 检查响应状态码，如果不是200则打印错误信息并返回None\\n- 如果请求成功，尝试将响应内容解析为JSON格式\\n- 如果JSON解析失败，打印错误信息并返回None\\n- 将成功解析的JSON响应结果通过OutPut1输出给下一个节点'
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True,'name':f'Input{i + 1}','Link':0,'IsLabel':False} for i in range(InPutNum)]
#**Initialize Outputs and Inputs arrays and assign names directly
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]


#**Assign properties to Inputs

for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'
#**Assign properties to Inputs

#**Function definition
def run_node(node):
    url = 'http://localhost:5111/send'
    data = {
        'message': node['Inputs'][0]['Context'],
        'to_user': node['Inputs'][1]['Context']
    }
    response = requests.post(url, json=data)
    # 检查响应状态码
    if response.status_code != 200:
        print("Error:", response.status_code, response.text)
        return None  # 或者返回一个错误信息
    try:
        return response.json()
    except json.JSONDecodeError:
        print("Failed to decode JSON from response:", response.text)
        return None  # 或者返回一个错误信息

#**Function definition