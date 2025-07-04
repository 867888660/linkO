import json
import logging
import os
# Define the number of outputs and inputs
OutPutNum = 5
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
Outputs[0]['name'] = 'Part1'
Outputs[1]['Kind'] = 'String'
Outputs[1]['name'] = 'Part2'
Outputs[2]['Kind'] = 'String'
Outputs[2]['name'] = 'Part3'
Outputs[3]['Kind'] = 'String'
Outputs[3]['name'] = 'Part4'
Outputs[4]['Kind'] = 'String'
Outputs[4]['name'] = 'Part5'

FunctionIntroduction='这是用来创建分割文本的会按照。或换行分割文本的节点。\n\n输入：文件内容。\n\n可创建输出节点：按照输出节点均等风切割文本。\n\n输出：分割后的文本。'
# Assign properties to Inputs and Outputs

def split_text_into_parts(text, num_parts):
    # Find all potential split points (newlines and periods)
    split_points = []
    for i, char in enumerate(text):
        if char == '\n' or char == '。':
            split_points.append(i)
    
    if not split_points:
        # If no split points found, return the entire text in first part
        return [text, "", ""]
    
    # Calculate ideal length for each part
    total_length = len(text)
    target_length = total_length / num_parts
    
    # Initialize result parts
    parts = []
    current_position = 0
    
    # Split text into desired number of parts
    for part_num in range(num_parts - 1):  # Process all but the last part
        ideal_position = int((part_num + 1) * target_length)
        
        # Find the closest split point to ideal position
        best_split_point = current_position
        min_diff = total_length
        
        for split_point in split_points:
            if split_point <= current_position:
                continue
            diff = abs(split_point - ideal_position)
            if diff < min_diff:
                min_diff = diff
                best_split_point = split_point
        
        # Add the part to results
        parts.append(text[current_position:best_split_point + 1])
        current_position = best_split_point + 1
    
    # Add the last part
    parts.append(text[current_position:])
    
    # Ensure we have exactly num_parts parts by adding empty strings if necessary
    while len(parts) < num_parts:
        parts.append("")
    
    return parts

def run_node(node):
    content = node['Inputs'][0]['Context']
    if not content:
        # Handle empty input
        for output in Outputs:
            output['Context'] = ""
        return Outputs
    
    # Split the text into three parts
    result_parts = split_text_into_parts(content, 5)
    result_parts = split_text_into_parts(content, 5)
    
    # Assign the parts to outputs
    for i, part in enumerate(result_parts):
        Outputs[i]['Context'] = part
    
    return Outputs