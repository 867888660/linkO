import json
import re
import http.client
import base64
from openai import OpenAI
#**Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 0
#**Define the number of outputs and inputs
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个基于 DeepSeek API 的大语言模型节点，支持文本和图像输入的多模态对话功能。该组件可以处理用户的文本提示和图像文件，通过 DeepSeek Reasoner 模型生成智能回复。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n核心功能包括图像文件的 Base64 编码转换、多模态消息构建、DeepSeek API 调用、响应内容的 JSON 格式化处理，以及输出结果的结构化封装。支持原始文本和 JSON 两种输出格式。\\n\\n参数\\n```yaml\\ninputs: []\\noutputs:\\n  - name: OutPut1\\n    type: string\\n    description: 模型生成的回复内容\\n```\\n\\n运行逻辑\\n- 清空并重新初始化输出数组\\n- 遍历输入节点，检测文件路径类型的输入\\n- 将图像文件转换为 Base64 编码格式\\n- 根据原始文本选择器处理导出提示词\\n- 构建包含文本和图像的多模态消息数组\\n- 使用 DeepSeek API 密钥初始化 OpenAI 客户端\\n- 限制最大令牌数不超过 8192\\n- 调用 deepseek-reasoner 模型进行对话生成\\n- 提取 API 响应中的内容文本\\n- 根据输出格式选择器处理响应内容\\n- 如果选择 JSON 格式，则解析并格式化 JSON 数据\\n- 将处理后的结果分配给相应的输出节点\\n- 记录 API 调用的令牌使用统计信息\\n- 返回包含生成内容和统计信息的输出数组'

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
    print('Test 1', messages)

    # Initialize the OpenAI client with DeepSeek API
    client = OpenAI(api_key="sk-81a62c0f3b614cf2a147f99ecf02ba64", base_url="https://api.deepseek.com")
    if node['max_tokens'] >8192:
        node['max_tokens'] = 8192

    # Make the API call
    response = client.chat.completions.create(
        model="deepseek-reasoner",
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