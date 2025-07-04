import json
import http.client
#**Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 0
#**Define the number of outputs and inputs

#**Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Kind': None,'Boolean':False, 'Id': f'Output{i + 1}', 'Context': None,'name':f'OutPut{i + 1}','Link':0,'Description':'answer'} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True,'name':f'Input{i + 1}','Link':0,'IsLabel':False} for i in range(InPutNum)]
#**Initialize Outputs and Inputs arrays and assign names directly
NodeKind = 'LLm'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]


#**Assign properties to Inputs

for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'
#**Assign properties to Inputs

#**Function definition
def run_node(node):
    Outputs.clear()
    for i in range(len(node['Outputs'])):
        Outputs.append(node['Outputs'][i])
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
    # 确保Outputs[key]是一个字典
    
        print(index,value)
        # 首先判断是否为字符串
        if(isinstance(value,str)):
            if(Outputs[index]['Kind']=='String'):
                Outputs[index]['Context']=value
            elif(Outputs[index]['Kind']=='Num'):
                Outputs[index]['Num']=int(value)
            elif(Outputs[index]['Kind']=='Boolean'):
                Outputs[index]['Boolean']=value

        print(json.dumps(Temp_dict, ensure_ascii=False))

    return Outputs
#**Function definition