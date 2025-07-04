import os
import json
import logging
# Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 2
# Define the number of outputs and inputs

# Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None,'Context': None,'Boolean':False,'Kind': None, 'Id': f'Output{i + 1}', 'name': 'WebOutput', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None,'Context': None,'Boolean':False, 'Kind': None, 'Id': f'Input{i + 1}',  'Isnecessary': True, 'name': 'WebInput', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]
# Initialize Outputs and Inputs arrays and assign names directly
FunctionIntroduction='组件功能  \n这是一个文件内容追加程序，能够向指定的文本文件追加内容。如果文件路径中的目录不存在，会自动创建；若文件本身不存在，则会自动创建空文件并进行内容追加。\n\n代码功能摘要  \n该程序的核心功能包括：检查和创建目标文件路径的目录，检查并创建目标文件（如果文件不存在），然后将指定的文本内容追加到文件末尾。内容追加时会使用 UTF-8 编码，确保文件支持中文等字符。\n\n参数  \n```yaml\ninputs:\n  - name: File_Path\n    type: string\n    required: true\n    description: 需要追加内容的文件路径\n    frozen: true\n  - name: Content\n    type: string\n    required: true\n    description: 需要追加到文件中的文本内容\n    frozen: false\noutputs:\n  - name: Result\n    type: string\n    description: 返回操作结果的提示信息\n```\n\n运行逻辑  \n- 检查输入的文件路径中的目录是否存在：\n  - 如果目录不存在，创建所需的目录结构。如果目录创建失败，记录错误日志并抛出异常。\n- 检查目标文件是否存在：\n  - 如果文件不存在，创建一个空文件。如果文件创建失败，记录错误日志并抛出异常。\n- 使用 UTF-8 编码打开文件，并追加内容：\n  - 在要追加的内容前后添加换行符，确保格式整洁。\n  - 将内容追加到文件末尾。如果写入失败，记录错误日志并抛出异常。\n- 返回操作结果提示信息：\"Content added to {filepath}\"'
NodeKind = 'Normal'
InputIsAdd = False
OutputIsAdd = False
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# Assign properties to Inputs and Outputs
Inputs[0]['Kind'] = 'String_FilePath'
Inputs[0]['name'] = 'File_Path'
Inputs[1]['Kind'] = 'String'
Inputs[1]['name'] = 'Content'
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Result'
# Assign properties to Inputs and Outputs

# Function definition
# Function definition
def run_node(node):
    filepath = node['Inputs'][0]['Context']
    content = node['Inputs'][1]['Context']
    
    # Combine path and filename
    
    # 确保目标文件的目录存在
    directory = os.path.dirname(filepath)
    if directory and not os.path.exists(directory):
        try:
            os.makedirs(directory)
            logging.info(f"Created directory: {directory}")
        except Exception as e:
            error_message = f"Failed to create directory {directory}: {str(e)}"
            logging.error(error_message)
            raise Exception(error_message)
    
    # 如果文件不存在，创建它
    if not os.path.exists(filepath):
        try:
            with open(filepath, 'w', encoding='utf-8') as file:  # Specify encoding here
                pass  # 创建空文件
            logging.info(f"Created new file: {filepath}")
        except Exception as e:
            error_message = f"Failed to create file {filepath}: {str(e)}"
            logging.error(error_message)
            raise Exception(error_message)
    
    # 写入内容
    try:
        with open(filepath, 'a', encoding='utf-8') as file:  # Specify encoding here
            file.write('\n' + content + '\n')
    except Exception as e:
        error_message = f"Failed to write to file {filepath}: {str(e)}"
        logging.error(error_message)
        raise Exception(error_message)

    Outputs[0]['Context'] = f"Content added to {filepath}"
    return Outputs
