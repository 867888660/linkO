import json
import re
import http.client
#**Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 0
#**Define the number of outputs and inputs

#**Initialize Outputs and Inputs arrays and assign names directly
FunctionIntroduction='组件功能（简述代码整体功能）\n这是一个调用大语言模型(LLM)接口的节点程序，通过HTTP请求调用OpenAI API获取AI回复并处理返回结果。\n\n代码功能摘要（概括核心算法或主要处理步骤）\n核心功能是构建HTTP请求调用OpenAI的o1-preview-ca模型，发送用户提示词获取AI回复，支持原始文本和JSON两种输出模式，并提供完整的token使用统计信息。\n\n参数\n```yaml\ninputs:\n  - name: ExportPrompt\n    type: string\n    required: true\n    description: 发送给AI的提示词内容\n  - name: OriginalTextSelector\n    type: string\n    required: true\n    description: 输出模式选择，可选值为OriginalText或Json\n    default: OriginalText\n  - name: temperature\n    type: number\n    required: true\n    description: 控制AI回复的随机性，范围0-1\n    default: 0.7\n  - name: max_tokens\n    type: integer\n    required: true\n    description: AI回复的最大token数量限制\n    default: 1000\n  - name: Top_p\n    type: number\n    required: true\n    description: 核采样参数，控制回复的多样性\n    default: 1.0\n  - name: frequency_penalty\n    type: number\n    required: true\n    description: 频率惩罚参数，减少重复内容\n    default: 0.0\n  - name: presence_penalty\n    type: number\n    required: true\n    description: 存在惩罚参数，鼓励谈论新话题\n    default: 0.0\noutputs:\n  - name: OutPut1\n    type: string\n    description: AI的回复内容，包含prompt_tokens、completion_tokens和total_tokens统计信息\n```\n\n运行逻辑\n- 清空并重新初始化输出数组，获取节点配置参数\n- 根据OriginalTextSelector模式处理ExportPrompt，如果是OriginalText模式则截取Please之前的内容\n- 建立HTTPS连接到api.chatanywhere.com.cn，构建包含模型参数和消息的JSON请求体\n- 设置请求头包括Authorization Bearer token和Content-Type，发送POST请求到/v1/chat/completions端点\n- 接收并解析API响应的JSON数据，提取AI回复内容\n- 如果是Json模式，使用ensure_wrapped_with_braces函数确保JSON格式正确，然后解析为字典对象\n- 调用process_input_str和clean_input_string等辅助函数处理和清理返回的文本内容\n- 根据输出模式将结果分配到对应的输出节点：Json模式按键值对分配，OriginalText模式直接赋值\n- 提取并记录token使用统计信息包括prompt_tokens、completion_tokens和total_tokens\n- 返回处理完成的Outputs数组，包含AI回复和完整的使用统计'
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
"claude-3-5-sonnet-20240620"
#**Function definition
def run_node(node):
    Outputs.clear()
    for i in range(len(node['Outputs'])):
        Outputs.append(node['Outputs'][i])
    messages = node["messages"]
    conn = http.client.HTTPSConnection("api.chatanywhere.com.cn")
    payload = json.dumps({
    "model": "o1-preview-ca",
    "temperature": node['temperature'],
    "max_tokens": node['max_tokens'],
    "top_p": node['Top_p'],
    "frequency_penalty": node['frequency_penalty'],
    "presence_penalty": node['presence_penalty'],
    "messages": messages,
    })
    headers = {
    'Authorization': 'Bearer sk-Cq3aggymPfzr7H5SFI5PnI0PFYlxrAXVsyE1tNwiiqVIQ9Mi',#sk-jgtdtSnaETuPKHc5WDsEx0bB0sVUOpWbhVPAt0rKpnwxger1
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

    def process_input_str(input_str):
        try:
            # 尝试解析为JSON
            parsed_json = json.loads(input_str)
            # 格式化输出以确保正确的JSON格式
            return json.dumps(parsed_json, indent=4, ensure_ascii=False)
        except json.JSONDecodeError as e:
            # 解析失败，返回原始字符串并附加错误信息
            return f"Invalid JSON string. Error: {str(e)}\nOriginal string: {input_str}"

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
    if (node['OriginalTextSelector'] =='Json'):
        Temp_dict = json.loads(ensure_wrapped_with_braces(Temp))
        print('测试2',Temp_dict)
    index=-1
    # Perform the transformation directly here.
    try:
        if (node['OriginalTextSelector'] =='Json'):
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
        else:
            Outputs[0]['Context'] = Temp
        Outputs[0]['prompt_tokens'] = jsonObj['usage']['prompt_tokens']
        Outputs[0]['completion_tokens'] = jsonObj['usage']['completion_tokens']
        Outputs[0]['total_tokens'] = jsonObj['usage']['total_tokens']
    except Exception as e:
        raise Exception(f"An error occurred: {e}. Temp_dict: {Temp_dict}")

    return Outputs
#**Function definition