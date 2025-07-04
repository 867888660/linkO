import json
import http.client
import requests
#**Define the number of outputs and inputs
OutPutNum = 2
InPutNum = 0
#**Define the number of outputs and inputs

#创建一个数组用于储存输出的值

#**Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Kind': None,'Boolean':False, 'Id': f'Output{i + 1}', 'Context': None,'name':f'OutPut{i + 1}','Link':0,'Description':''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True,'name':f'Input{i + 1}','Link':0,'IsLabel':True} for i in range(InPutNum)]
#**Initialize Outputs and Inputs arrays and assign names directly
NodeKind = 'Trigger'
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
        #print('测试阿松大',messages)
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
        print('测试阿23er3松大',Array)
        return Array
#**Function definition