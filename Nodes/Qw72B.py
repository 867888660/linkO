import json
import re
import http.client
import base64
from openai import OpenAI
import unicodedata
#**Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 0
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个基于阿里云通义千问模型的大语言模型节点，支持文本和图像输入，能够根据系统提示词和用户输入生成智能回复。\n\n代码功能摘要（概括核心算法或主要处理步骤）\\n该节点通过OpenAI兼容接口调用通义千问模型，支持图像转Base64编码处理，具备JSON格式输出解析功能，并提供完整的token使用统计信息。\n\n参数\\n```yaml\\ninputs:\\n  - name: 可动态创建输入节点\\n    type: string\\n    required: false\\n    description: 支持文本和图像文件输入，图像会自动转换为Base64格式\\noutputs:\\n  - name: OutPut1\\n    type: string\\n    description: 模型生成的回复内容，支持原始文本或JSON格式输出\\n```\n\n运行逻辑\\n- 清空并重新初始化输出数组\\n- 遍历输入节点，检测图像文件并转换为Base64编码\\n- 根据OriginalTextSelector设置构建系统提示词\\n- 组装消息数组，包含系统提示、用户输入和图像内容\\n- 调用阿里云通义千问API，传入温度、最大token数、top_p等参数\\n- 获取模型响应并提取内容\\n- 如果选择JSON模式，使用内置JSON解析器处理响应\\n- 清理和格式化JSON内容，去除代码块标记和控制字符\\n- 根据输出节点类型分配解析后的数据\\n- 记录prompt_tokens、completion_tokens和total_tokens使用情况\\n- 返回包含生成内容和统计信息的输出数组'
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
    if node['max_tokens'] >8192:
        node['max_tokens'] = 8192

    # Make the API call
    response = client.chat.completions.create(
        model="qwen-plus-latest",
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
    if node['OriginalTextSelector'] == 'Json':
        Temp_dict = json.loads(string_to_json(Temp))
        print('Test 2', Temp_dict)
    print('Test 1 Temp', Temp)
    if node['OriginalTextSelector'] == 'Json':
        Temp_dict = json.loads(string_to_json(Temp))
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