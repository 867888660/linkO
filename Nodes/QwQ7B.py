import json
import re
import http.client
import base64
from openai import OpenAI
#**Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 0
#**Define the number of outputs and inputs
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个基于阿里云通义千问2.5-7B模型的大语言模型节点，支持文本和图像输入，能够根据系统提示词和用户输入生成智能回复。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n该节点通过OpenAI兼容接口调用通义千问模型，支持图像转Base64编码处理，具备JSON格式输出解析功能，并提供完整的token使用统计。核心处理包括消息构建、API调用、响应解析和输出格式化。\\n\\n参数\\n```yaml\\ninputs: []\\noutputs:\\n  - name: OutPut1\\n    type: string\\n    description: 模型生成的回复内容\\n```\\n\\n运行逻辑\\n- 清空并重新初始化输出数组\\n- 遍历输入节点，检测文件路径类型的输入并转换为Base64编码\\n- 根据OriginalTextSelector设置构建系统提示词\\n- 构建包含系统消息和用户消息的对话数组\\n- 将Base64编码的图像添加到消息中\\n- 使用OpenAI客户端调用通义千问API，设置温度、最大token数等参数\\n- 获取模型响应内容\\n- 根据OriginalTextSelector判断是否需要JSON解析\\n- 如果是JSON模式，使用正则表达式清理和解析响应\\n- 将解析后的内容分配给对应的输出节点\\n- 记录API调用的token使用情况\\n- 返回包含生成内容和统计信息的输出数组'

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
    client = OpenAI(api_key="sk-d08a424af9d44655934ad7117c77ebd2", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    if node['max_tokens'] >8192:
        node['max_tokens'] = 8192

    # Make the API call
    response = client.chat.completions.create(
        model="qwen2.5-7b-instruct-1m",
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