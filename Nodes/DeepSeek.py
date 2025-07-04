import json
import re
import http.client
import base64
from openai import OpenAI
import unicodedata
#**Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 0
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个基于 DeepSeek API 的大语言模型节点，支持文本和图像输入，能够根据系统提示词和用户输入生成智能回复。该组件集成了图像转 Base64 编码、JSON 解析、多种输出格式处理等功能。\n\n代码功能摘要（概括核心算法或主要处理步骤）\\n核心功能包括：图像文件转 Base64 编码处理、构建包含系统提示词和用户输入的消息体、调用 DeepSeek Chat API 进行推理、支持 JSON 格式输出解析和多种数据类型转换、记录 token 使用情况统计。\n\n参数\\n```yaml\\ninputs: []\\noutputs:\\n  - name: OutPut1\\n    type: string\\n    description: 模型生成的回复内容\\n```\n\n运行逻辑\\n- 清空并重新初始化输出数组\\n- 遍历输入节点，检测文件路径类型的输入并转换为 Base64 编码\\n- 根据 OriginalTextSelector 设置构建系统提示词\\n- 构建包含系统消息和用户消息的对话数组\\n- 将 Base64 编码的图像添加到消息体中\\n- 使用 DeepSeek API 密钥初始化 OpenAI 客户端\\n- 调用 chat.completions.create 方法进行推理，传入模型参数\\n- 获取 API 响应内容\\n- 如果输出格式为 JSON，则解析并提取结构化数据\\n- 根据输出节点的数据类型进行相应转换和赋值\\n- 记录 prompt_tokens、completion_tokens 和 total_tokens 使用情况\\n- 返回处理后的输出数组'
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
    client = OpenAI(api_key="sk-81a62c0f3b614cf2a147f99ecf02ba64", base_url="https://api.deepseek.com")
    if node['max_tokens'] >8192:
        node['max_tokens'] = 8192
    print('Test message', messages)
    # Make the API call
    response = client.chat.completions.create(
        model="deepseek-chat",
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

    def _strip_code_fences(raw: str) -> str:
        """去掉常见 ```json … ``` 或 ``` … ``` 代码块包裹。"""
        raw = raw.strip()
        raw = re.sub(r'^```(?:json)?', '', raw, flags=re.I).strip()
        raw = re.sub(r'```$', '', raw).strip()
        return raw

    def _find_json_region(raw: str) -> str:
        """
        返回原串中 **第一个** 平衡的大括号片段。
        只在“引号之外”统计括号深度，防止值里本身含有 { }。
        """
        raw = _strip_code_fences(raw)
        first = raw.find('{')
        if first == -1:
            raise ValueError('未找到 "{"')

        depth = 0
        in_str = False
        esc = False
        for i in range(first, len(raw)):
            ch = raw[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        return raw[first:i + 1]
        raise ValueError('大括号不匹配')

    def _escape_newlines_inside_strings(js: str) -> str:
        """
        JSON 规范里字符串内不能出现裸换行符。
        把位于引号内部的 \n / \r 转义成 \\n。
        """
        out, in_str, esc = [], False, False
        for ch in js:
            if in_str:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == '"':
                    in_str = False
                elif ch in '\n\r':
                    out.append('\\n')
                    continue
            else:
                if ch == '"':
                    in_str = True
            out.append(ch)
        return ''.join(out)

    def _basic_clean(text: str) -> str:
        """去掉控制字符并做 NFC Unicode 归一化。"""
        text = unicodedata.normalize('NFC', text)
        return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)

    # ---------- 对外主函数 ----------

    def string_to_json(input_str: str, indent: int = 4) -> str:
        """
        把混杂字符串 → 格式化 JSON（str）。
        解析失败抛出 json.JSONDecodeError / ValueError，便于上层捕获。
        """
        cleaned   = _basic_clean(input_str)
        json_part = _find_json_region(cleaned)
        json_part = _escape_newlines_inside_strings(json_part)
        obj       = json.loads(json_part)         # 这里如有语法问题会直接抛错
        return json.dumps(obj, ensure_ascii=False, indent=indent)
    
    print('Test 1 Temp', Temp)
    if node['OriginalTextSelector'] == 'Json' :
        Temp_dict = json.loads(string_to_json(Temp))
        print('Test 2', Temp_dict)
    
    index = -1
    try:
        if node['OriginalTextSelector'] == 'Json' :
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