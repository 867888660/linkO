import json
import re
import http.client
import base64
from openai import OpenAI
#**Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 0
#**Define the number of outputs and inputs
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个基于阿里云通义千问QWQ-Plus模型的大语言模型节点，支持文本和图像输入，能够进行推理思考并生成回答。\n\n代码功能摘要（概括核心算法或主要处理步骤）\\n该组件通过OpenAI兼容接口调用阿里云通义千问QWQ-Plus模型，支持图像转Base64编码处理，具备流式输出和推理过程展示功能，可根据配置输出原始文本或JSON格式结果。\n\n参数\\n```yaml\\ninputs:\\n  - name: 动态输入\\n    type: string\\n    required: false\\n    description: 可动态创建多个输入节点，支持文本和图像文件输入\\noutputs:\\n  - name: OutPut1\\n    type: string\\n    description: 模型生成的回答内容，可包含推理过程和token使用统计\\n```\n\n运行逻辑（用 - 列表描写详细流程）\\n- 清空并重新构建输出数组，准备接收节点配置的输出格式\\n- 遍历输入节点，识别图像文件类型输入并转换为Base64编码格式\\n- 根据OriginalTextSelector配置构建系统提示词，合并SystemPrompt和ExprotAfterPrompt\\n- 构建消息数组，包含系统角色提示和用户问题，添加Base64编码的图像内容\\n- 初始化OpenAI客户端，配置阿里云通义千问API端点和密钥\\n- 限制max_tokens参数不超过8192，调用chat.completions.create进行流式生成\\n- 处理流式响应，分别收集推理过程(reasoning_content)和最终回答(content)\\n- 实时打印思考过程和完整回复，提供用户交互体验\\n- 根据OriginalTextSelector配置处理输出格式，支持原始文本或JSON解析\\n- 如果选择JSON格式，使用正则表达式清理和验证JSON结构\\n- 将处理后的结果分配到对应的输出节点，支持字符串、数字、布尔值类型\\n- 保存推理内容和token使用统计信息到输出节点\\n- 返回包含所有输出结果的数组，供后续节点使用'

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
    client = OpenAI(
        api_key="sk-d08a424af9d44655934ad7117c77ebd2", 
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    
    if node['max_tokens'] > 8192:
        node['max_tokens'] = 8192

    # Make the API call with streaming enabled
    completion = client.chat.completions.create(
        model="qwq-plus",
        messages=messages,
        temperature=node['temperature'],
        max_tokens=node['max_tokens'],
        top_p=node['Top_p'],
        frequency_penalty=node['frequency_penalty'],
        presence_penalty=node['presence_penalty'],
        stream=True
    )

    reasoning_content = ""  # Store complete reasoning process
    answer_content = ""     # Store complete response
    is_answering = False    # Flag to track when reasoning ends and answering begins
    
    print("\n" + "=" * 20 + "思考过程" + "=" * 20 + "\n")
    
    # Process streaming response
    for chunk in completion:
        # If chunk.choices is empty, this might be usage information
        if not chunk.choices:
            if hasattr(chunk, 'usage'):
                usage = chunk.usage
                break
        else:
            delta = chunk.choices[0].delta
            # Process reasoning content if available
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content is not None:
                print(delta.reasoning_content, end='', flush=True)
                reasoning_content += delta.reasoning_content
            elif hasattr(delta, 'content') and delta.content is not None:
                # Start of actual response
                if not is_answering and delta.content != "":
                    print("\n" + "=" * 20 + "完整回复" + "=" * 20 + "\n")
                    is_answering = True
                
                # Print and store response content
                print(delta.content, end='', flush=True)
                answer_content += delta.content
    
    Temp = answer_content  # Use the collected answer content
    
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
    Temp_dict = None
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
        
        # Store reasoning content if needed
        if reasoning_content:
            Outputs[0]['reasoning_content'] = reasoning_content
        
        # Add token usage if available
        if 'usage' in locals():
            Outputs[0]['prompt_tokens'] = usage.prompt_tokens
            Outputs[0]['completion_tokens'] = usage.completion_tokens
            Outputs[0]['total_tokens'] = usage.total_tokens
    except Exception as e:
        raise Exception(f"An error occurred: {e}. Temp: {Temp}, Temp_dict: {Temp_dict if Temp_dict else 'None'}")

    return Outputs

