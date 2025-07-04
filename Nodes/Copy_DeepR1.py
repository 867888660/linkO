import json
import re
import http.client
import base64
import requests
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

def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        encoded_image = base64.b64encode(image_file.read())
        return encoded_image.decode('utf-8')

def run_node(node):
    Outputs.clear()
    for i in range(len(node['Outputs'])):
        Outputs.append(node['Outputs'][i])
    
    TempArray = []
    for i in range(len(node['Inputs'])):
        print('Test 2', node['Inputs'][i]['Kind'])
        if 'FilePath' in node['Inputs'][i]['Kind']:
            # Convert image file to Base64 and add to TempArray
            TempArray.append(image_to_base64(node['Inputs'][i]['Context']))
    
    ExprotPrompt = node['ExprotPrompt']
    if node['OriginalTextSelector'] == 'OriginalText':
        ExprotPrompt = ExprotPrompt.split('Please')[0]

    messages = [{'role': 'user', 'content': ExprotPrompt}]
    
    # Add images to the messages
    for base64_image in TempArray:
        messages.append({
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]
        })
    print('Test 1', messages)
    payload = {
        "model": "deepseek-ai/DeepSeek-R1",
        "temperature": node['temperature'],
        "max_tokens": node['max_tokens'],
        "top_p": node['Top_p'],
        "frequency_penalty": node['frequency_penalty'],
        "presence_penalty": node['presence_penalty'],
        "messages": messages,
        "response_format": {"type": "text"},
        "tools": [
            {
                "type": "function",
                "function": {
                    "description": "<string>",
                    "name": "<string>",
                    "parameters": {},
                    "strict": False
                }
            }
        ]
    }
    headers = {
        'Authorization': 'Bearer sk-abgfvmqpthzukzwmbogisjojfecjbzqsxiotuchzvntugfvl',
        "Content-Type": "application/json"
    }

    # Using requests instead of http.client
    response = requests.post("https://api.siliconflow.cn/v1/chat/completions", json=payload, headers=headers)
    
    if response.status_code == 200:
        jsonObj = response.json()
        Temp = jsonObj['choices'][0]['message']['content']
    else:
        raise Exception(f"Request failed with status code {response.status_code}: {response.text}")

    def process_input_str(input_str):
        try:
            parsed_json = json.loads(input_str)
            return json.dumps(parsed_json, indent=4, ensure_ascii=False)
        except json.JSONDecodeError as e:
            return f"Invalid JSON string. Error: {str(e)}\nOriginal string: {input_str}"

    def ensure_wrapped_with_braces(input_str):
        if input_str.startswith('```json') and input_str.endswith('```'):
            input_str = input_str[7:-3]  # Remove ```json and ```

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
        quotes = re.findall(r'"', input_string)
        if len(quotes) % 2 != 0:
            raise ValueError("Mismatched quotes")

        cleaned_string = re.sub(r'\(.*?\)', '', input_string)
        cleaned_string = re.sub(r'[\x00-\x1F\x7F]', '', cleaned_string)
        return cleaned_string

    print('Test 1 Temp', Temp)
    if node['OriginalTextSelector'] == 'Json':
        Temp_dict = json.loads(ensure_wrapped_with_braces(Temp))
        print('Test 2', Temp_dict)
    
    index = -1
    try:
        if node['OriginalTextSelector'] == 'Json':
            for key, value in Temp_dict.items():
                index += 1
                if Outputs[index]['Kind'] == 'String':
                    Outputs[index]['Context'] = value
                elif Outputs[index]['Kind'] == 'Num':
                    Outputs[index]['Num'] = int(value)
                elif Outputs[index]['Kind'] == 'Boolean':
                    Outputs[index]['Boolean'] = value
        else:
            Outputs[0]['Context'] = Temp
        Outputs[0]['prompt_tokens'] = jsonObj['usage']['prompt_tokens']
        Outputs[0]['completion_tokens'] = jsonObj['usage']['completion_tokens']
        Outputs[0]['total_tokens'] = jsonObj['usage']['total_tokens']
    except Exception as e:
        raise Exception(f"An error occurred: {e}. Temp_dict: {Temp_dict}")

    return Outputs