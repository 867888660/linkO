import json
import logging
import os
# Define the number of outputs and inputs
OutPutNum = 2
InPutNum = 3
# Define the number of outputs and inputs

# Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': f'Output{i + 1}', 'name': 'WebOutput', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': f'Input{i + 1}', 'Isnecessary': True if i == 0 else False, 'name': 'WebInput', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]
# Initialize Outputs and Inputs arrays and assign names directly

NodeKind = 'Normal'
InputIsAdd = False
OutputIsAdd = False
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# Assign properties to Inputs and Outputs

for input in Inputs:
    input['Kind'] = 'String'
    input['name'] = 'WebInput'
    if input['Id'] == 'Input1':
        input['Isnecessary'] = True
    else:
        input['Isnecessary'] = False
Inputs[0]['Kind'] = 'String_FilePath'
Inputs[0]['name'] = 'File_Path'
Inputs[1]['name'] = 'File_Name'
Inputs[2]['name'] = 'Content'
Inputs[1]['Kind'] = 'String'
Inputs[2]['Kind'] = 'String'
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Result'
Outputs[1]['Kind'] = 'String'
Outputs[1]['name'] = 'File_Path'
FunctionIntroduction='这是一个创建和保存TXT文本文件的组件。\\n\\n代码功能摘要：该组件接收文件路径、文件名和内容三个输入参数，将内容以UTF-8编码格式保存为.txt文件，并返回保存状态和完整文件路径。\\n\\n参数：\\n```yaml\\ninputs:\\n  - name: File_Path\\n    type: string\\n    required: true\\n    description: 文件保存的目录路径\\n  - name: File_Name\\n    type: string\\n    required: false\\n    description: 要创建的文件名称（不含扩展名）\\n  - name: Content\\n    type: string\\n    required: false\\n    description: 要写入文件的文本内容\\noutputs:\\n  - name: Result\\n    type: string\\n    description: 文件保存操作的结果状态信息\\n  - name: File_Path\\n    type: string\\n    description: 完整的文件保存路径\\n```\\n\\n运行逻辑：\\n- 从输入节点获取文件保存路径、文件名称和文件内容\\n- 对文件名进行预处理，移除其中的换行符\\n- 将文件路径和文件名拼接，形成完整路径\\n- 自动为文件添加.txt扩展名\\n- 使用UTF-8编码方式将内容写入到指定文件\\n- 输出文件保存成功的状态信息到Result\\n- 输出完整的文件保存路径到File_Path'
# Assign properties to Inputs and Outputs


# Function definition
def run_node(node):
    file_path = node['Inputs'][0]['Context']
    file_name = node['Inputs'][1]['Context']
    content = node['Inputs'][2]['Context']
    file_name = file_name.replace('\n','')
    # Combine path and filename
    full_path = f"{file_path}/{file_name}"
    #按txt格式保存
    full_path = full_path + '.txt'
    
    # Write content to file using utf-8 encoding
    with open(full_path, 'w', encoding='utf-8') as file:
        file.write(content)
    
    Outputs[0]['Context'] = f"File saved to {full_path}"
    Outputs[1]['Context'] = full_path
    return Outputs
# Function definition
