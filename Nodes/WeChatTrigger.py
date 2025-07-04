import json
import http.client
import requests
#**Define the number of outputs and inputs
OutPutNum = 2
InPutNum = 0
#**Define the number of outputs and inputs

#创建一个数组用于储存输出的值
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个监听信息的被动触发节点，用于从本地5111端口获取未回复的消息，并将消息发送者和内容传递给后续节点进行处理。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n通过HTTP GET请求获取消息列表，遍历查找第一条未回答的消息（Isanswered=False），将消息的发送者昵称和内容分别输出，支持异常处理机制。\\n\\n参数\\n```yaml\\ninputs: []\\noutputs:\\n  - name: OutPut1\\n    type: string\\n    description: 发送消息的用户昵称\\n  - name: OutPut2\\n    type: string\\n    description: 发送的消息内容\\n```\\n\\n运行逻辑\\n- 初始化输出数组，将所有输出的Context设置为None\\n- 向本地127.0.0.1:5111/messages端点发送GET请求获取消息列表\\n- 解析响应的JSON数据获取消息数组\\n- 遍历消息列表，查找第一条Isanswered字段为False的未回复消息\\n- 找到未回复消息后，将消息的nickname赋值给第一个输出，将content赋值给第二个输出\\n- 将输出数组添加到结果数组中，设置接收标志为True并跳出循环\\n- 如果发生网络请求异常或JSON解析错误，打印错误信息并返回None\\n- 如果成功获取到未回复消息，返回包含输出数据的数组；否则不返回任何值'

#**Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Kind': None,'Boolean':False, 'Id': f'Output{i + 1}', 'Context': None,'name':f'OutPut{i + 1}','Link':0,'Description':''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True,'name':f'Input{i + 1}','Link':0,'IsLabel':True} for i in range(InPutNum)]
#**Initialize Outputs and Inputs arrays and assign names directly
NodeKind = 'passivityTrigger'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]


#**Assign properties to Inputs

for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'
    input['Context'] = '杨雨轩1'
#**Assign properties to Inputs

#**Function definition
def run_node(node):
    Array = []
  
    for output in Outputs:
        output['Context'] = None
    Isaccepted = False
    # 假设你的 Flask 应用可以接受 POST 方法的 /messages 路由
    url = "http://127.0.0.1:5111/messages"
    try:
        response = requests.get(url)  # 修改为GET请求，因为你的Flask定义了GET
        response.raise_for_status()  # 将引发异常的非200响应
        messages = response.json()
        for message in messages:
            if message['Isanswered'] == False:  # 假设 Isanswered 是布尔类型
                Outputs[0]['Context'] = message['nickname']
                Outputs[1]['Context'] = message['content']
                Array.append(Outputs)
                Isaccepted = True
                break
    except requests.RequestException as e:
        print("Network error:", e)
        return None
    except json.JSONDecodeError:
        print("Failed to decode JSON from response:", response.text)
        return None
    if Isaccepted:
        return Array
#**Function definition