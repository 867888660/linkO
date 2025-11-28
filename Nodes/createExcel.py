import json
import logging
import os
import openpyxl
# Define the number of outputs and inputs
OutPutNum = 2
InPutNum = 2
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
Inputs[1]['Kind'] = 'String'
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Result'
Outputs[1]['Kind'] = 'String'
Outputs[1]['name'] = 'File_Path'
FunctionIntroduction='组件功能：这是一个创建空白Excel文件的节点，用于在指定路径下生成新的Excel工作簿文件。\\n\\n代码功能摘要：接收文件路径和文件名参数，使用openpyxl库创建空白Excel工作簿并保存到指定位置，返回操作结果和完整文件路径。\\n\\n参数：\\n```yaml\\ninputs:\\n  - name: File_Path\\n    type: string\\n    required: true\\n    description: 指定Excel文件的保存目录路径\\n  - name: File_Name\\n    type: string\\n    required: false\\n    description: 要创建的Excel文件名称（可不含.xlsx后缀）\\noutputs:\\n  - name: Result\\n    type: string\\n    description: 返回文件创建的执行结果信息\\n  - name: File_Path\\n    type: string\\n    description: 返回新创建Excel文件的完整路径\\n```\\n\\n运行逻辑：\\n- 获取输入的文件保存路径和文件名参数\\n- 清理文件名中的换行符等特殊字符\\n- 检查文件名是否包含.xlsx后缀，如果没有则自动添加\\n- 使用os.path.join()将文件路径和文件名组合成完整路径\\n- 调用openpyxl.Workbook()创建新的空白Excel工作簿对象\\n- 使用workbook.save()方法将工作簿保存到指定的完整路径\\n- 如果创建成功，将成功信息和完整文件路径分别赋值给两个输出\\n- 如果过程中发生异常，捕获错误并记录到日志，将错误信息输出到Result，File_Path输出为空字符串\\n- 返回包含操作结果和文件路径的输出数组'
# Assign properties to Inputs and Outputs

# Function definition
def run_node(node):
    file_path = node['Inputs'][0]['Context']
    file_name = node['Inputs'][1]['Context']
    file_name = file_name.replace('\n','')
    
    # 确保文件名以.xlsx结尾
    if not file_name.endswith('.xlsx'):
        file_name += '.xlsx'

    # 组合完整路径
    full_path = os.path.join(file_path, file_name)

    try:
        # 创建新的Excel工作簿
        workbook = openpyxl.Workbook()
        # 保存工作簿
        workbook.save(full_path)
        
        Outputs[0]['Context'] = f"Excel file created successfully at {full_path}"
        Outputs[1]['Context'] = full_path
    except Exception as e:
        error_message = f"Error creating Excel file: {str(e)}"
        logging.error(error_message)
        Outputs[0]['Context'] = error_message
        Outputs[1]['Context'] = ""

    return Outputs
# Function definition
