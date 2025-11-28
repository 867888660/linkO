import os
import json
import logging

# Define the number of outputs and inputs
OutPutNum = 2
InPutNum = 2

# Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': f'Output{i + 1}', 'name': 'WebOutput', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': f'Input{i + 1}', 'Isnecessary': True , 'name': 'WebInput', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]

NodeKind = 'Normal'
InputIsAdd = False
OutputIsAdd = False
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# Assign properties to Inputs and Outputs
Inputs[0]['Kind'] = 'String_FilePath'
Inputs[0]['name'] = 'Floder_Path'
Inputs[1]['name'] = 'Floder_Name'
Inputs[1]['Kind'] = 'String'
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Result'
Outputs[1]['Kind'] = 'String'
Outputs[1]['name'] = 'Full_Path'
FunctionIntroduction='组件功能：这是一个文件夹创建节点，用于在指定路径下创建新的文件夹，并返回创建结果和完整路径信息。\\n\\n代码功能摘要：通过接收目标路径和文件夹名称，使用os.path.join拼接完整路径，检查路径是否存在，如不存在则使用os.makedirs创建文件夹，最后返回操作结果和完整路径。\\n\\n参数：\\n```yaml\\ninputs:\\n  - name: Floder_Path\\n    type: string\\n    required: true\\n    description: 目标文件夹的父级路径\\n  - name: Floder_Name\\n    type: string\\n    required: true\\n    description: 需要创建的文件夹名称\\noutputs:\\n  - name: Result\\n    type: string\\n    description: 文件夹创建操作的结果信息\\n  - name: Full_Path\\n    type: string\\n    description: 创建的文件夹的完整路径\\n```\\n\\n运行逻辑：\\n- 从输入节点获取目标路径(Floder_path)和文件夹名称(Floder_name)\\n- 使用os.path.join将路径和文件夹名称拼接成完整的文件夹路径\\n- 通过os.path.exists检查该完整路径是否已存在\\n- 如果路径不存在，使用os.makedirs创建新文件夹(包括必要的父级目录)\\n- 将操作结果信息格式化为\"File saved to {完整路径}\"并输出到Result\\n- 将完整的文件夹路径输出到Full_Path\\n- 返回包含两个输出结果的Outputs数组'

# Function definition
def run_node(node):
    Floder_path = node['Inputs'][0]['Context']
    Floder_name = node['Inputs'][1]['Context']
    
    # Combine path and folder name
    full_folder_path = os.path.join(Floder_path, Floder_name)
    
    # Check if the folder exists
    if not os.path.exists(full_folder_path):
        # Create the folder if it doesn't exist
        os.makedirs(full_folder_path)
    Outputs[0]['Context'] = f"File saved to {full_folder_path}"
    Outputs[1]['Context'] = full_folder_path
    
    return Outputs