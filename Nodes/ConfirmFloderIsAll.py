import os
import json
import logging

# Define the number of outputs and inputs
OutPutNum = 3
InPutNum = 2

# Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None,'Context': None,'Boolean':False,'Kind': None, 'Id': f'Output{i + 1}', 'name': 'WebOutput', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None,'Context': None,'Boolean':False, 'Kind': None, 'Id': f'Input{i + 1}',  'Isnecessary': True, 'name': 'WebInput', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]

# Function introduction and node properties
FunctionIntroduction = '用于确认文件是否存在。\n\n输入：文件路径，文件历史路径。\n\n输出：布尔值代表文件夹是否齐全,结果，基本路径。'
NodeKind = 'Normal'
InputIsAdd = False
OutputIsAdd = False
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# Assign properties to Inputs and Outputs
Inputs[0]['Kind'] = 'String'
Inputs[0]['name'] = 'History_Path'
Inputs[1]['Kind'] = 'String'
Inputs[1]['name'] = 'Now_Message'
Outputs[0]['Kind'] = 'Boolean'
Outputs[0]['name'] = 'Confirm'
Outputs[1]['Kind'] = 'String'
Outputs[1]['name'] = 'Result'
Outputs[2]['Kind'] = 'String'
Outputs[2]['name'] = 'Base_Path'

def run_node(node):
    History_Path = node['Inputs'][0]['Context']
    Now_Message = node['Inputs'][1]['Context']
    
    # 标准化路径，处理多重斜杠的问题
    Now_Message = os.path.normpath(Now_Message)
    base_path = os.path.normpath(os.path.dirname(Now_Message))
    
    if '@TempFiles' in base_path:
        try:
            current_dir = os.path.abspath(os.path.dirname(__file__))
            parent_dir = os.path.dirname(current_dir)
            parent_temp_path = os.path.normpath(os.path.join(parent_dir, 'TempFiles'))
            
            if os.path.exists(parent_temp_path):
                base_path = os.path.normpath(base_path.replace('@TempFiles', parent_temp_path))
            else:
                error_msg = "'TempFiles' directory not found in the parent directory."
                node['Outputs'][0]['Boolean'] = False
                node['Outputs'][1]['Context'] = error_msg
                node['Outputs'][2]['Context'] = ""
                return node['Outputs']
                
        except Exception as e:
            error_msg = f"Error processing @TempFiles path: {str(e)}"
            node['Outputs'][0]['Boolean'] = False
            node['Outputs'][1]['Context'] = error_msg
            node['Outputs'][2]['Context'] = ""
            return node['Outputs']

    # 获取基础路径下所有数字命名的文件夹
    existing_numbers = []
    try:
        for item in os.listdir(base_path):
            full_path = os.path.join(base_path, item)
            if os.path.isdir(full_path) and item.isdigit():
                existing_numbers.append(item)
    except Exception as e:
        error_msg = f"Error reading directory: {str(e)}"
        node['Outputs'][0]['Boolean'] = False
        node['Outputs'][1]['Context'] = error_msg
        node['Outputs'][2]['Context'] = base_path
        return node['Outputs']
    
    # 检查History_Path中是否包含所有数字文件夹的路径
    missing_paths = []
    for number in existing_numbers:
        expected_path = os.path.normpath(os.path.join(base_path, number))
        path_found = False
        
        # 在History_Path中查找每个路径
        for line in History_Path.strip().split('\n'):
            if 'content:' in line:
                history_path = os.path.normpath(line.split('content:')[1].strip())
                if history_path == expected_path:
                    path_found = True
                    break
        
        if not path_found:
            missing_paths.append(expected_path)
    
    # 更新输出
    all_paths_exist = len(missing_paths) == 0
    node['Outputs'][0]['Boolean'] = all_paths_exist
    
    # 设置结果消息
    if all_paths_exist:
        node['Outputs'][1]['Context'] = "所有文件夹路径都已包含在历史记录中"
    else:
        missing_paths_str = "\n".join(missing_paths)
        node['Outputs'][1]['Context'] = f"以下文件夹路径未在历史记录中找到：\n{missing_paths_str}"
    
    # 设置基础路径
    node['Outputs'][2]['Context'] = base_path
    
    return node['Outputs']