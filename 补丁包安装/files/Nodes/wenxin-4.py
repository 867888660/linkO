import json
import re
import http.client
import os, json, re, ssl, certifi, http.client, traceback
import unicodedata
import base64
#**Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 0
#**Define the number of outputs and inputs
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个基于Claude Sonnet模型的大语言模型节点，通过HTTPS API调用实现智能对话和文本生成功能。支持系统提示词配置、温度等参数调节，并可选择原始文本或JSON格式输出。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n核心功能包括构建对话消息体、发送HTTPS请求到ChatAnywhere API、接收并解析模型响应。支持JSON格式智能解析，能够自动提取JSON内容并分配到多个输出节点，同时记录token使用统计信息。\\n\\n参数\\n```yaml\\ninputs: []\\noutputs:\\n  - name: OutPut1\\n    type: string\\n    description: 模型生成的回答内容或解析后的JSON数据\\n```\\n\\n运行逻辑\\n- 根据节点配置构造系统提示词，结合SystemPrompt和ExprotAfterPrompt\\n- 创建包含system和user角色的消息数组，system角色承载提示词，user角色承载具体问题\\n- 建立SSL安全连接到api.chatanywhere.tech，配置请求头包含API密钥和内容类型\\n- 构建请求载荷，包含模型名称、温度、最大token数、top_p等参数\\n- 发送POST请求到/v1/chat/completions端点，获取模型响应\\n- 解析返回的JSON数据，提取模型生成的文本内容\\n- 根据OriginalTextSelector设置判断输出格式：原始文本直接输出，JSON格式则进行深度解析\\n- JSON解析包括去除代码块标记、查找平衡括号区域、转义换行符、清理控制字符等步骤\\n- 将解析后的JSON键值对分配到对应的输出节点，支持动态扩展输出节点数量\\n- 记录prompt_tokens、completion_tokens、total_tokens等使用统计信息到输出节点'

#**Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Kind': None,'Boolean':False, 'Id': f'Output{i + 1}', 'Context': None,'name':f'OutPut{i + 1}','Link':0,'Description':'answer'} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Boolean':False,'Context': None, 'Isnecessary': True,'name':f'Input{i + 1}','Link':0,'IsLabel':False} for i in range(InPutNum)]
#**Initialize Outputs and Inputs arrays and assign names directly
NodeKind = 'LLm'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]


#**Assign properties to Inputs

for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'


# ---------- 全局常量 ----------
API_HOST = "api.chatanywhere.tech"
API_PATH = "/v1/chat/completions"
MODEL    = "chatgpt-4o-latest"    # 建议先用已确认可用的
MAX_TOK  = 16000

# ---------- run_node ----------
def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        encoded_image = base64.b64encode(image_file.read())
        return encoded_image.decode('utf-8')
def run_node(node: dict):
    Outputs.clear()
    for i in range(len(node['Outputs'])):
        Outputs.append(node['Outputs'][i])
    messages = node["messages"]
    # 3) HTTPS 连接
    ctx  = ssl.create_default_context(cafile=certifi.where())
    conn = http.client.HTTPSConnection(API_HOST, context=ctx, timeout=120)

    payload = json.dumps({
        "model": MODEL,
        "temperature": node.get("temperature", 0.7),
        "max_tokens": min(node.get("max_tokens", 1024), MAX_TOK),
        "top_p": node.get("Top_p", 1.0),
        "frequency_penalty": node.get("frequency_penalty", 0),
        "presence_penalty": node.get("presence_penalty", 0),
        "messages":messages,
    })
    API_KEY = "sk-QQpePsr8ICLdM0OC6QsoW835cbrpn7FkhtXecq4gIPcFvLHV"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "User-Agent":    "DebugScript/0.1",
        "Content-Type":  "application/json"
    }

    # 4) 发送请求
    
    conn.request("POST", API_PATH, payload, headers)
    res  = conn.getresponse()
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
    
    index = -1
    try:
        if node['OriginalTextSelector'] == 'Json':
            diff = len(Temp_dict) - len(Outputs)
            if diff > 0:                          # Temp_dict 键比 Outputs 多
                # 用第 0 个输出当模板，浅拷贝补齐
                template = Outputs[0].copy()
                template.update({'Context': None, 'Num': None, 'Boolean': False})
                for _ in range(diff):
                    Outputs.append(template.copy())
            for key, value in Temp_dict.items():
                index += 1
                if index >= len(Outputs):          # ← 防止 Temp_dict 里键比 Outputs 多
                    break                          #   超出就直接跳出（也可用 continue）
                if Outputs[index]['Kind'] == 'String':
                    Outputs[index]['Context'] = value
                elif Outputs[index]['Kind'] == 'Num':
                    Outputs[index]['Num'] = int(value)
                elif Outputs[index]['Kind'] == 'Boolean':
                    Outputs[index]['Boolean'] = value
                print('Test 3', value)
        else:
            Outputs[0]['Context'] = Temp

        # 把 token 统计写入第一个 Output（或按需写入所有）
        Outputs[0].update({
            'prompt_tokens':     jsonObj['usage']['prompt_tokens'],
            'completion_tokens': jsonObj['usage']['completion_tokens'],
            'total_tokens':      jsonObj['usage']['total_tokens'],
        })
    except Exception as e:
        raise Exception(f"An error occurred: {e}. Temp_dict: {Temp_dict}")

    return Outputs