import json
import requests
import os
#**Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 2
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
    url = 'http://localhost:5111/sendFile'
    data = {
        'file_path': node['Inputs'][0]['Context'],
        'nick_name': node['Inputs'][1]['Context']
    }
    #确认路径是否存在
    if not os.path.exists(data['file_path']):
        print(f"Error: file {data['file_path']} not exists")
        return None
    else:
        print(f"Sending file {data['file_path']} to {data['nick_name']}")
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