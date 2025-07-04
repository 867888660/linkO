import json
import re
import http.client
import base64
from openai import OpenAI
import os
import logging
import time
from PIL import Image
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个基于阿里云通义千问视觉语言模型的AI对话节点，支持文本和图像的多模态输入处理，能够根据系统提示词和用户输入生成智能回复。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n该组件通过OpenAI兼容接口调用通义千问2.5-VL模型，将输入的图像文件转换为Base64编码后与文本提示一起发送给模型，支持JSON格式和原始文本两种输出模式，并提供完整的token使用统计信息。\\n\\n参数\\n```yaml\\ninputs: []\\noutputs:\\n  - name: OutPut1\\n    type: string\\n    description: 模型生成的回复内容\\n```\\n\\n运行逻辑\\n- 清空并重新初始化输出数组\\n- 遍历输入节点，识别图像文件类型的输入\\n- 将图像文件转换为Base64编码格式\\n- 根据OriginalTextSelector设置构建系统提示词\\n- 构建包含系统提示、用户提示和图像数据的消息数组\\n- 使用OpenAI客户端调用阿里云通义千问2.5-VL模型接口\\n- 设置模型参数包括温度、最大token数、top_p等\\n- 获取模型响应内容\\n- 根据输出格式选择器处理响应：JSON格式则解析并分配到对应输出，原始文本则直接输出\\n- 记录token使用情况包括输入token、输出token和总token数\\n- 返回处理后的输出结果'
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
    
    messages = node["messages"]
    # Initialize the OpenAI client with DeepSeek API
    client = OpenAI(api_key="sk-194e194cc95a4951a33d8666a6fffa80", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    if node['max_tokens'] >2000:
        node['max_tokens'] = 2000

    # Make the API call
    response = client.chat.completions.create(
        model="qwen2.5-vl-72b-instruct",#qwen2.5-vl-72b-instruct  qwen2.5-vl-7b-instruct qwen-vl-plus
        messages=messages,
        temperature=node['temperature'],
        max_tokens=node['max_tokens'],
        top_p=node['Top_p'],
        frequency_penalty=node['frequency_penalty'],
        presence_penalty=node['presence_penalty'],
        stream=False
    )

    # Extract the response content
    Temp = response.choices[0].message.content

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
        Outputs[0]['prompt_tokens'] = response.usage.prompt_tokens
        Outputs[0]['completion_tokens'] = response.usage.completion_tokens
        Outputs[0]['total_tokens'] = response.usage.total_tokens
    except Exception as e:
        raise Exception(f"An error occurred: {e}. Temp_dict: {Temp_dict}")

    return Outputs