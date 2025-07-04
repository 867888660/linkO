import json
import re
import http.client
import base64
import requests
import unicodedata
#**Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 0
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个豆包大语言模型调用组件，用于通过豆包API进行文本生成和多模态对话，支持文本和图像输入，可根据配置返回原始文本或JSON格式的结构化数据。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n该组件集成豆包API调用功能，支持系统提示词和用户提示词配置，具备图像转Base64编码处理能力，提供多种输出格式选择（原始文本/JSON），并包含完整的JSON解析和清理机制，同时记录token使用情况。\\n\\n参数\\n```yaml\\ninputs: []\\noutputs:\\n  - name: OutPut1\\n    type: string\\n    description: 豆包模型生成的回答内容\\n```\\n\\n运行逻辑\\n- 清空并重新初始化输出数组，准备接收节点配置的输出结构\\n- 遍历输入节点，将图像文件转换为Base64编码格式，存储到临时数组中\\n- 根据OriginalTextSelector配置构建系统提示词，组合SystemPrompt和ExprotAfterPrompt\\n- 构建消息数组，包含系统角色和用户角色的提示内容\\n- 将Base64编码的图像添加到消息数组中，支持多模态输入\\n- 配置豆包API调用参数，包括模型名称、温度、最大token数、top_p等参数\\n- 发送POST请求到豆包API端点，获取模型生成的响应内容\\n- 检查API响应状态，如果失败则抛出异常信息\\n- 提取响应中的生成内容和token使用统计信息\\n- 根据OriginalTextSelector配置选择输出格式处理方式\\n- 如果选择JSON格式，则调用字符串转JSON函数进行结构化解析\\n- 使用正则表达式和字符串处理技术清理和提取有效的JSON内容\\n- 将解析后的结果按照输出节点的数据类型进行分配和转换\\n- 记录prompt_tokens、completion_tokens和total_tokens使用情况\\n- 返回包含生成内容和统计信息的完整输出数组'
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

    # === 豆包API调用部分 ===
    # 你需要在此处填写你的API Key
    API_KEY = "371e174e-ce1d-4bc7-bd64-2247b5158dcc"
    API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"  # 豆包Chat API
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    payload = {
        "model": "doubao-1-5-thinking-vision-pro-250428",  # 可根据实际模型更换
        "messages": messages,
        "temperature": node['temperature'],
        "max_tokens": min(node['max_tokens'], 8192),
        "top_p": node['Top_p'],
        "frequency_penalty": node['frequency_penalty'],
        "presence_penalty": node['presence_penalty'],
        "stream": False
    }
    response = requests.post(API_URL, headers=headers, data=json.dumps(payload))
    if response.status_code != 200:
        raise Exception(f"Doubao API调用失败: {response.status_code} {response.text}")
    result = response.json()
    # 豆包API返回结构适配
    Temp = result['choices'][0]['message']['content']
    
    usage = result.get('usage', {})

    def _strip_code_fences(raw: str) -> str:
        """去掉常见 ```json … ``` 或 ``` … ``` 代码块包裹。"""
        raw = raw.strip()
        raw = re.sub(r'^```(?:json)?', '', raw, flags=re.I).strip()
        raw = re.sub(r'```$', '', raw).strip()
        return raw

    def _find_json_region(raw: str) -> str:
        """
        返回原串中 **第一个** 平衡的大括号片段。
        只在"引号之外"统计括号深度，防止值里本身含有 { }。
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
        text = unicodedata.normalize('NFC', text)
        return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)

    def string_to_json(input_str: str, indent: int = 4) -> str:
        cleaned   = _basic_clean(input_str)
        try:
            json_part = _find_json_region(cleaned)
            json_part = _escape_newlines_inside_strings(json_part)
            obj       = json.loads(json_part)
            return json.dumps(obj, ensure_ascii=False, indent=indent)
        except Exception as e:
            raise Exception(f"string_to_json error: {e}. 原始内容: {input_str}")

    if node['OriginalTextSelector'] == 'Json':
        Temp_dict = json.loads(string_to_json(Temp))
    
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
        Outputs[0]['prompt_tokens'] = usage.get('prompt_tokens', None)
        Outputs[0]['completion_tokens'] = usage.get('completion_tokens', None)
        Outputs[0]['total_tokens'] = usage.get('total_tokens', None)
    except Exception as e:
        raise Exception(f"An error occurred: {e}. Temp_dict: {Temp_dict if 'Temp_dict' in locals() else ''}")

    return Outputs