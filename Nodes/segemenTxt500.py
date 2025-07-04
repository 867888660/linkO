import json
import logging
import os

# Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 3

# Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': f'Output{i + 1}', 'name': 'WebOutput', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': f'Input{i + 1}', 'Isnecessary': True if i == 0 else False, 'name': 'WebInput', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]

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
Outputs[0]['name'] = 'Part'
Inputs[1]['Kind'] = 'String'
Inputs[1]['name'] = 'max_length'

Inputs[2]['Kind'] = 'String'
Inputs[2]['name'] = 'min_last_length'

FunctionIntroduction = '这是用来创建分割文本的会按照。或换行分割文本的节点。\n\n输入：文件内容。\n\n可创建输出节点：按照输出节点均等风切割文本。\n\n输出：分割后的文本。'

def split_text_into_parts(text, max_length, min_last_length):
    sentence_endings = '。！？!?\n'
    total_length = len(text)
    
    # 如果总长度小于最大长度，直接返回整个文本
    if total_length <= max_length:
        return [text]
    
    parts = []
    start = 0
    
    while start < total_length:
        # 确定本次分割的目标长度范围
        remaining_text = text[start:]
        remaining_length = len(remaining_text)
        
        # 如果剩余文本长度小于min_last_length且不是第一部分，需要与前一部分合并
        if remaining_length < min_last_length and parts:
            parts[-1] += remaining_text
            break
            
        # 在max_length范围内寻找最后一个结束符
        end = start + max_length
        if end > total_length:
            end = total_length
            
        # 在目标长度范围内查找最后一个结束符
        last_ending = None
        for i in range(min(end, total_length), start, -1):
            if text[i-1] in sentence_endings:
                last_ending = i
                break
        
        # 如果找到了合适的结束符，就在结束符处分割
        if last_ending:
            parts.append(text[start:last_ending])
            start = last_ending
        else:
            # 如果没找到结束符，就在max_length处强制分割
            if end < total_length:
                parts.append(text[start:end])
                start = end
            else:
                # 处理最后一段文本
                last_part = text[start:]
                if parts and len(last_part) < min_last_length:
                    parts[-1] += last_part
                else:
                    parts.append(last_part)
                break
    
    return parts

def run_node(node):
    content = node['Inputs'][0]['Context']
    max_length = int(node['Inputs'][1]['Context'])
    min_last_length = int(node['Inputs'][2]['Context'])
    
    if not content:
        Outputs[0]['Context'] = ""
        return Outputs
    
    result_parts = split_text_into_parts(content, max_length, min_last_length)
    Outputs[0]['Context'] = "\n**^^**\n".join(result_parts)
    
    return Outputs
def run_node(node):
    content = node['Inputs'][0]['Context']
    max_length = int(node['Inputs'][1]['Context'])
    min_last_length = int(node['Inputs'][2]['Context'])
    if not content:
        # Handle empty input
        for output in Outputs:
            output['Context'] = ""
        return Outputs
    
    # Split the text into parts
    result_parts = split_text_into_parts(content,max_length,min_last_length)
    Outputs[0]['Context'] =  ""
    print('测试\n\大撒大撒',result_parts)
    for i, part in enumerate(result_parts):
        print('测试',i,'擦速度擦拭\n撒旦撒',part)
        Outputs[0]['Context']+='\n'+"**^^**" +'\n'+ part

    
    return Outputs
