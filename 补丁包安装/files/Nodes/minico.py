import json
import re
import http.client
import base64
import os
import logging
import time
import unicodedata
from PIL import Image
#**Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 0
#**Define the number of outputs and inputs

#**Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Kind': None,'Boolean':False, 'Id': f'Output{i + 1}', 'Context': None,'name':f'OutPut{i + 1}','Link':0,'Description':'answer','prompt_tokens':0,'completion_tokens': 0, 'total_tokens': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True,'name':f'Input{i + 1}','Link':0,'IsLabel':False} for i in range(InPutNum)]
#**Initialize Outputs and Inputs arrays and assign names directly
NodeKind = 'LLm'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='组件功能（基于GPT-4模型的多模态大语言模型节点，支持文本和图片输入）\n\n代码功能摘要（通过HTTP请求调用ChatGPT API，处理文本和图片输入，支持JSON格式化输出和原始文本输出两种模式）\n\n参数：\n```yaml\ninputs:\n  - name: SystemPrompt\n    type: string\n    required: true\n    description: 系统提示词，定义AI助手的角色和行为规范\n  - name: ExprotAfterPrompt\n    type: string\n    required: false\n    description: 导出后的补充提示词，用于增强系统提示\n  - name: prompt\n    type: string\n    required: true\n    description: 用户输入的问题或对话内容\n  - name: OriginalTextSelector\n    type: string\n    required: true\n    description: 输出格式选择器，可选值为Json或OriginalText\n    default: OriginalText\n    frozen: true\n  - name: temperature\n    type: number\n    required: true\n    description: 控制输出随机性的温度参数，范围0-2\n    default: 0.7\n  - name: max_tokens\n    type: integer\n    required: true\n    description: 最大输出token数量限制\n    default: 1000\n  - name: Top_p\n    type: number\n    required: true\n    description: 核采样参数，控制输出多样性\n    default: 1.0\n  - name: frequency_penalty\n    type: number\n    required: true\n    description: 频率惩罚参数，减少重复内容\n    default: 0.0\n  - name: presence_penalty\n    type: number\n    required: true\n    description: 存在惩罚参数，鼓励谈论新话题\n    default: 0.0\noutputs:\n  - name: OutPut1\n    type: string\n    description: 模型返回的回答内容或JSON格式化结果\n```\n\n运行逻辑：\n- 清空并重新初始化输出数组，复制节点配置的输出结构\n- 遍历输入数组，检测FilePath类型的输入并转换为base64格式图片数据\n- 根据OriginalTextSelector参数构建系统提示词，如果选择OriginalText则只使用SystemPrompt\n- 构建消息数组，包含系统角色消息和用户消息\n- 将所有base64格式的图片作为用户消息添加到消息数组中\n- 构建API请求载荷，包含模型参数和消息内容\n- 设置HTTP请求头，包含授权token和内容类型\n- 建立HTTPS连接到ChatGPT API服务器并发送POST请求\n- 接收并解析API响应的JSON数据\n- 提取模型回复内容到临时变量Temp\n- 如果选择Json格式输出，使用内置的JSON清理和解析函数处理回复内容\n- 根据输出格式选择器分配结果到对应的输出字段\n- 记录API使用的token统计信息到输出结果中\n- 返回包含处理结果和token统计的输出数组'

#**Assign properties to Inputs

for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'
#**Assign properties to Inputs
#**Function definition
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
    
    systemPrompt = f"{node['SystemPrompt']}\n{node['ExprotAfterPrompt']}"
    if node['OriginalTextSelector'] == 'OriginalText': 
        systemPrompt = node['SystemPrompt'] 
    messages = [
        {
            "role": "system",
            "content": systemPrompt
            # 如果 ExprotAfterPrompt 只是给模型的补充指令，放在 system 里即可；
            # 若它是要在生成后追加到答案里的模板，则不应该写进提示，而是在外部拼接。
        },
        {
            "role": "user",
            "content": node['prompt']          # 只放真正的用户问题
        }
    ]
    
    # Add images to the messages
    for base64_image in TempArray:
        messages.append({
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]
        })
    print('Test 1', messages)
    payload = json.dumps({
        "model": "gpt-4.1-nano",
        "temperature": node['temperature'],
        "max_tokens": node['max_tokens'],
        "top_p": node['Top_p'],
        "frequency_penalty": node['frequency_penalty'],
        "presence_penalty": node['presence_penalty'],
        "messages": messages
    })
    headers = {
        'Authorization': 'Bearer sk-QtGJDuACy18rdE0uPWbbIzk3jhMCtFoqZlzFSn4h7PeNldVf',
        'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
        'Content-Type': 'application/json'
    }

    conn = http.client.HTTPSConnection("api.chatanywhere.tech")
    conn.request("POST", "/v1/chat/completions", payload, headers)
    res = conn.getresponse()
    data = res.read()
    jsonObj = json.loads(data.decode("utf-8"))
    Temp = jsonObj['choices'][0]['message']['content']
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
        Outputs[0]['prompt_tokens'] = jsonObj['usage']['prompt_tokens']
        Outputs[0]['completion_tokens'] = jsonObj['usage']['completion_tokens']
        Outputs[0]['total_tokens'] = jsonObj['usage']['total_tokens']
    except Exception as e:
        raise Exception(f"An error occurred: {e}. Temp_dict: {Temp_dict}")

    return Outputs