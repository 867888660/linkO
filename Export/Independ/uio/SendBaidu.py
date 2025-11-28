import json
import requests
#**Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 1
#**Define the number of outputs and inputs

#**Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Kind': None, 'Id': f'Output1{i + 1}', 'Context': None,'name':f'OutPut{i + 1}','Link':0} for i in range(OutPutNum)]
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
    url = 'http://localhost:1056/sendmessage'
    data = {
        'message': node['Inputs'][0]['Context'],
        'app_name':'app2'
    }
    response = requests.post(url, json=data)
    # 检查响应状态码
    if response.status_code != 200:
        print("Error:", response.status_code, response.text)
        return None  # 或者返回一个错误信息
    try:
        Temp=response.json()
        Outputs[0]['Context']= Temp['message']
        return Outputs
    except json.JSONDecodeError:
        print("Failed to decode JSON from response:", response.text)
        return None  # 或者返回一个错误信息

#**Function definition