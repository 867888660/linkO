import json
import http.client
import requests
import re
import copy
import chardet
import logging
import os

# **Define the number of outputs and inputs**
OutPutNum = 4
InPutNum = 2
# **Define the number of outputs and inputs**

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]
NodeKind = 'ArrayTrigger'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='这是一个文本分割处理节点，用于读取文件并按指定分隔符将内容分割成多个片段进行批量处理。\\n\\n该节点实现了智能文件读取和灵活的文本分割功能，支持多种编码格式和自定义分割模式，将单个文件内容转换为可逐一处理的文本片段数组。\\n\\n```yaml\\ninputs:\\n  - name: file_path\\n    type: file\\n    required: true\\n    description: 需要分割的文件路径\\n  - name: divide_sign\\n    type: string\\n    required: false\\n    description: 文本分隔符，支持普通字符串或自定义模式\\n    default: \\\"\\\\n\\\\n\\\"\\noutputs:\\n  - name: context\\n    type: string\\n    description: 分割后的文本内容片段\\n  - name: num\\n    type: integer\\n    description: 当前文本片段的序号\\n  - name: Is_Last\\n    type: boolean\\n    description: 是否为最后一个文本片段\\n  - name: Total_Num\\n    type: integer\\n    description: 文本片段总数\\n```\\n\\n- 文件读取阶段：尝试使用多种编码格式（utf-8、gb2312、gbk、gb18030、ascii）自动识别并读取指定文件内容\\n- 分隔符解析：检查输入的分隔符是否为自定义模式（格式：字符1@<X>字符2），如果是则解析为正则表达式模式\\n- 文本分割处理：根据分隔符类型选择相应的分割方法，自定义模式使用正则表达式分割并保留分隔符，普通模式直接按字符串分割\\n- 内容过滤：移除分割后的空白片段，确保输出内容的有效性\\n- 输出构建：为每个有效的文本片段创建包含四个输出字段的对象，包括片段内容、序号、是否最后一个的标识和总片段数\\n- 数组生成：使用深度复制确保每个输出对象的独立性，返回完整的片段数组供后续节点逐一处理'

# **Assign properties to Inputs**
Outputs[0]['Kind'] = 'String'
Outputs[1]['Kind'] = 'Num'
Outputs[0]['name'] = 'context'
Outputs[1]['name'] = 'num'
Outputs[2]['name'] = 'Is_Last'
Outputs[2]['Kind'] = 'Boolean'
Outputs[3]['name'] = 'Total_Num'
Outputs[3]['Kind'] = 'Num'
for input in Inputs:
    input['Kind'] = 'String_FilePath'
Inputs[0]['name'] = 'file_path'
Inputs[1]['name'] = 'divide_sign'
Inputs[1]['Isnecessary'] = False
Inputs[1]['Kind'] = 'String'
# **Assign properties to Inputs**

def parse_custom_pattern(divide_sign):
    # 检查是否包含自定义模式
    if '@<' in divide_sign and '>' in divide_sign:
        # 提取字符1和字符2
        parts = divide_sign.split('@<')
        char1 = parts[0]
        char2 = parts[1].split('>')[1]
        # 返回用于匹配的正则表达式模式
        return f"{char1}[^\n]*?{char2}"
    return None

def split_by_custom_pattern(content, pattern):
    # 使用正则表达式分割内容
    # 保留分隔符
    splits = re.split(f"({pattern})", content)
    # 过滤空白内容
    filtered_splits = []
    current_content = ""
    
    for i, split in enumerate(splits):
        if re.match(pattern, split):  # 如果是分隔符
            if current_content:  # 如果有累积的内容
                filtered_splits.append(current_content.strip())
            current_content = ""  # 重置累积内容
        else:
            current_content += split  # 累积内容
    
    # 添加最后一段内容
    if current_content:
        filtered_splits.append(current_content.strip())
    
    return [s for s in filtered_splits if s.strip()]

# **Function definition**
def run_node(node):
    Array = []
    events = []
    # 读取输入文件路径
    file_path = node['Inputs'][0]['Context']
    Divide_Sign = node['Inputs'][1]['Context']

    
    print("文件路径:", file_path)  # 调试信息，查看文件路径
    
    try:
        # 尝试多种编码方式读取文件
        encodings_to_try = ['utf-8', 'gb2312', 'gbk', 'gb18030', 'ascii']
        content = None
        
        for encoding in encodings_to_try:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                print(f"成功使用 {encoding} 编码读取文件")
                break  # 如果成功读取，跳出循环
            except UnicodeDecodeError:
                print(f"使用 {encoding} 编码读取失败，尝试下一个编码")
                continue
        
        if content is None:
            raise Exception("无法使用任何已知编码读取文件")
        
        # 检查是否有自定义的分隔符格式
        custom_pattern = parse_custom_pattern(Divide_Sign) if Divide_Sign else None
        
        if custom_pattern:
            events = split_by_custom_pattern(content, custom_pattern)
        else:
            # 使用原有的分割逻辑
            if Divide_Sign == '' or Divide_Sign is None or Divide_Sign.lower() in ['none', 'null', '*n']:
                Divide_Sign = '\n\n'  # 默认分隔符为双回车
            events = content.split(Divide_Sign)
        
        print("分割后的事件:", content, events)
        
        # 过滤掉空白或只包含空格的事件
        events = [event.strip() for event in events if event.strip()]
        
        if not events:
            print("Warning: No valid content found in file after filtering")
            return None

        # 存储事件到输出节点
        for event in events:
            try:
                # 更新上下文
                Outputs[0]['Context'] = event
                # 这个数组的序号
                Outputs[1]['Num'] = len(Array)  # 记录当前事件在数组中的位置
                Outputs[2]['Boolean'] = False  # 是否是最后一个事件
                # 这个数组的总长度
                Outputs[3]['Num'] = len(events)  # 记录数组的总长度

                # 如果是最后一个事件
                if Outputs[1]['Num'] == len(events) - 1:
                    Outputs[2]['Boolean'] = True
                
                # 添加独立的输出对象
                Array.append(copy.deepcopy(Outputs))  # 使用 deep copy 来避免引用问题
            except Exception as e:
                print(f"Error processing event: {e}")

    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

    # 返回 Array
    print('分割后的事件数组:', Array)
    return Array
