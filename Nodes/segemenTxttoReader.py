import json
import logging
import os
# Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 1
# Define the number of outputs and inputs

# Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': f'Output{i + 1}', 'name': 'WebOutput', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': f'Input{i + 1}', 'Isnecessary': True if i == 0 else False, 'name': 'WebInput', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]
# Initialize Outputs and Inputs arrays and assign names directly

NodeKind = 'Normal'
InputIsAdd = True
OutputIsAdd = True
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# Assign properties to Inputs and Outputs

for input in Inputs:
    input['Kind'] = 'String'
    input['name'] = 'WebInput'
    if input['Id'] == 'Input1':
        input['Isnecessary'] = True
    else:
        input['Isnecessary'] = False
Inputs[0]['name'] = 'Content'
Inputs[0]['Kind'] = 'String'
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Reader'

FunctionIntroduction='这是用来创建分割文本将文本转化成字幕的节点。\n\n输入：文件内容。\n\n输出：分割后的文本。'
# Assign properties to Inputs and Outputs

def process_text_to_subtitles(content):
    # 定义分割标点
    main_separators = ['。', '！', '？']
    # 移除 ',' 因为它已经包含在中文逗号中
    secondary_separators = ['，', '；', '：']
    
    # 理想的行长度（中文字符）
    ideal_line_length = 15
    
    # 替换所有换行和多余空格
    content = ' '.join(content.split())
    
    # 预处理：移除所有引号
    content = content.replace('"', '').replace('"', '').replace('"', '').replace('“', '').replace('”', '')
    
    # 初始化结果列表
    subtitle_lines = []
    
    # 先按主要分隔符分割成句子
    temp_sentences = []
    current = ''
    
    for char in content:
        current += char
        if char in main_separators:
            temp_sentences.append(current.strip())
            current = ''
    if current:
        temp_sentences.append(current.strip())
    
     # 修改句子处理逻辑
    for sentence in temp_sentences:
        # 增加长度判断的灵活性
        if len(sentence) <= ideal_line_length + 5:  # 允许一定的长度浮动
            subtitle_lines.append(sentence)
            continue
            
        # 改进分段逻辑
        parts = []
        current_part = ''
        for char in sentence:
            current_part += char
            if char in secondary_separators:
                if len(current_part.strip()) > 5:  # 确保分段不会太短
                    parts.append(current_part.strip())
                    current_part = ''
                
        # 处理最后一部分
        if current_part.strip() and len(current_part.strip()) > 5:
            parts.append(current_part.strip())
        
        # 将处理后的部分添加到字幕行
        subtitle_lines.extend(parts)
    
    # 清理每一行
    cleaned_lines = []
    for line in subtitle_lines:
        # 清理行首尾的标点和空格
        line = line.strip(',.，。！？；：')
        line = line.strip()
        if line:
            cleaned_lines.append(line)
    
    # 用双换行符连接所有字幕行
    return '\n\n'.join(cleaned_lines)


def run_node(node):
    content = node['Inputs'][0]['Context']
    subtitles = process_text_to_subtitles(content)
    Outputs[0]['Context'] = subtitles
    return Outputs
