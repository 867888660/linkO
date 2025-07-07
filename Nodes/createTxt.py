import json
import logging
import os
import traceback
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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


# Helper function to parse arguments from a string format
def parse_args_from_string(arg_string):
    """
    Parse arguments from a string like:
    { "File_Path": "F://linkO//TempFiles", "File_Name": "杨瀚森", "Content": "杨瀚森的身体数据..." }
    """
    try:
        # Try to parse as JSON
        if isinstance(arg_string, str):
            # Clean up the string if it contains quotes and escape characters
            arg_string = arg_string.replace('\\"', '"').replace("\\'", "'")
            # Try to extract JSON content if it's embedded in a string
            json_match = re.search(r'\{.*\}', arg_string)
            if json_match:
                arg_string = json_match.group(0)
            
            try:
                args = json.loads(arg_string)
                return args
            except json.JSONDecodeError:
                # If JSON parsing fails, try to extract key-value pairs manually
                args = {}
                # Extract key-value pairs using regex
                pattern = r'"([^"]+)":\s*"([^"]*)"'
                matches = re.findall(pattern, arg_string)
                for key, value in matches:
                    args[key] = value
                return args
    except Exception as e:
        logger.error(f"Failed to parse arguments: {e}")
        return {}


# Function definition
def run_node(node):
    try:
        # Validate node structure
        if 'Inputs' not in node:
            raise ValueError("Node missing 'Inputs' field")
        
        # Special handling for different input formats
        file_path = None
        file_name = None
        content = None
        
        # Case 1: Standard format with multiple inputs
        if len(node['Inputs']) >= 3:
            try:
                file_path = node['Inputs'][0].get('Context', '')
                file_name = node['Inputs'][1].get('Context', 'unnamed_file')
                content = node['Inputs'][2].get('Context', '')
            except Exception as e:
                logger.error(f"Error extracting inputs from standard format: {str(e)}")
        
        # Case 2: Arguments provided in a single input with JSON-like format
        elif len(node['Inputs']) > 0 and 'Context' in node['Inputs'][0]:
            try:
                # Check if the input contains a JSON-like structure
                input_context = node['Inputs'][0].get('Context', '')
                if isinstance(input_context, str) and '{' in input_context and '}' in input_context:
                    args = parse_args_from_string(input_context)
                    file_path = args.get('File_Path', '')
                    file_name = args.get('File_Name', 'unnamed_file')
                    content = args.get('Content', '')
                    logger.info(f"Parsed arguments from string: {file_path}, {file_name}, content length: {len(content)}")
            except Exception as e:
                logger.error(f"Error parsing arguments from string: {str(e)}")
        
        # Case 3: Check for 'Tools' field with parameters
        elif 'Tools' in node and isinstance(node['Tools'], list) and len(node['Tools']) > 0:
            try:
                tool = node['Tools'][0]
                if 'Inputs' in tool and isinstance(tool['Inputs'], list):
                    tool_inputs = tool['Inputs']
                    if len(tool_inputs) >= 3:
                        file_path = tool_inputs[0].get('Parameters', '')
                        file_name = tool_inputs[1].get('Parameters', 'unnamed_file')
                        content = tool_inputs[2].get('Parameters', '')
                        if content == 'auto_input' and '_arg' in node['Inputs'][0]:
                            # Try to extract content from the _arg field
                            arg_context = node['Inputs'][0].get('Context', '')
                            args = parse_args_from_string(arg_context)
                            content = args.get('Content', '')
            except Exception as e:
                logger.error(f"Error extracting inputs from Tools field: {str(e)}")
        
        # Log the extracted values
        logger.info(f"Extracted values: file_path={file_path}, file_name={file_name}, content_length={len(content) if content else 0}")
        
        # Validate extracted values
        if not file_path:
            raise ValueError("File_Path is empty or could not be extracted")
        
        if not file_name:
            file_name = 'unnamed_file'
            
        # Clean file name
        file_name = file_name.replace('\n', '').strip()
        
        # Create directory if it doesn't exist
        if not os.path.exists(file_path):
            os.makedirs(file_path, exist_ok=True)
            logger.info(f"Created directory: {file_path}")
        
        # Combine path and filename
        full_path = os.path.join(file_path, file_name)
        
        # Add .txt extension if not present
        if not full_path.lower().endswith('.txt'):
            full_path = full_path + '.txt'
            
        logger.info(f"Saving file to: {full_path}")
        
        # Write content to file using utf-8 encoding
        with open(full_path, 'w', encoding='utf-8') as file:
            file.write(content)
        
        # Set outputs
        Outputs[0]['Context'] = "文件保存成功"
        Outputs[1]['Context'] = full_path
        
        return Outputs
        
    except Exception as e:
        error_msg = f"Error in createTxt: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        
        # Return error in outputs instead of raising exception
        Outputs[0]['Context'] = f"错误: {str(e)}"
        Outputs[1]['Context'] = ""
        return Outputs
# Function definition
