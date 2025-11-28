import json
import re
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
    print('测试gpt3.5trubo',Outputs)
    print(node['ExprotPrompt'])
    conn = http.client.HTTPSConnection("api.chatanywhere.com.cn")
    payload = json.dumps({
    "model": "gpt-3.5-turbo",
    "temperature": node['temperature'],
    "max_tokens": node['max_tokens'],
    "top_p": node['Top_p'],
    "frequency_penalty": node['frequency_penalty'],
    "presence_penalty": node['presence_penalty'],
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

    def process_input_str(input_str):
        is_in_quotes = False
        new_str = ''
        i = 0
        while i < len(input_str):
            if input_str[i] == '"' and (i == 0 or input_str[i-1] != '\\'):
                is_in_quotes = not is_in_quotes
                new_str += input_str[i]
            elif not is_in_quotes:
                if input_str[i] == '(':
                    while i < len(input_str) and input_str[i] != ')':
                        i += 1  # 跳过圆括号及其中的内容
                    if i < len(input_str):
                        i += 1  # 跳过关闭的圆括号
                else:
                    new_str += input_str[i]
            else:
                new_str += input_str[i]
            i += 1
        return new_str

# 结合之前的函数
    # 结合之前的函数
    def ensure_wrapped_with_braces(input_str):
        if input_str.startswith('```json') and input_str.endswith('```'):
            input_str = input_str[7:-3]  # 移除 ```json 和 ```

        # 清理输入字符串
        input_str = clean_input_string(input_str)

        first_brace_pos = input_str.find('{')
        corresponding_closing_brace_pos = -1
        open_brace_count = 0

        if first_brace_pos == -1:
            return f'{{{input_str}}}'

        for i in range(first_brace_pos, len(input_str)):
            if input_str[i] == '{':
                open_brace_count += 1
            elif input_str[i] == '}':
                open_brace_count -= 1
                if open_brace_count == 0:
                    corresponding_closing_brace_pos = i
                    break

        input_str = input_str[first_brace_pos:corresponding_closing_brace_pos + 1]
        return process_input_str(input_str)

    def clean_input_string(input_string):
        # 检查成对引号
        quotes = re.findall(r'"', input_string)
        if len(quotes) % 2 != 0:
            raise ValueError("引号不成对")

        # 清除括号及其中的内容
        cleaned_string = re.sub(r'\(.*?\)', '', input_string)

        # 移除无效的控制字符
        cleaned_string = re.sub(r'[\x00-\x1F\x7F]', '', cleaned_string)

        return cleaned_string

    # Transform the Temp string into a JSON object, assuming it's structured as a dictionary.
    print('测试1Temp',Temp)
    Temp_dict = json.loads(ensure_wrapped_with_braces(Temp))
    print('测试2',Temp_dict)
    index=-1
    # Perform the transformation directly here.
    try:
        for key, value in Temp_dict.items():
            index += 1
            # 确保Outputs[key]是一个字典
            print(index, value)
            # 首先判断是否为字符串或者布尔值
            if Outputs[index]['Kind'] == 'String':
                Outputs[index]['Context'] = value
            elif Outputs[index]['Kind'] == 'Num':
                Outputs[index]['Num'] = int(value)
            elif Outputs[index]['Kind'] == 'Boolean':
                Outputs[index]['Boolean'] = value
    except Exception as e:
        raise Exception(f"An error occurred: {e}. Temp_dict: {Temp_dict}")


    return Outputs
#**Function definition