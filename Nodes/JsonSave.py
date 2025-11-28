import json
import re
import os

# Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 3

# Initialize Outputs and Inputs arrays and assign names directly
FunctionIntroduction='组件功能（简述代码整体功能）\\n\\n这是一个JSON数据处理和保存的节点，用于将输入的内容提取为JSON对象并保存到指定文件路径，支持追加模式和中文内容处理。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n\\n核心功能包括：使用正则表达式提取{}包围的JSON对象，清理和标准化文本格式（处理空格和中文标点），将提取内容转换为Python字典，检查目标文件是否存在并支持数据追加，最终以UTF-8编码保存JSON文件。\\n\\n参数\\n\\n```yaml\\ninputs:\\n  - name: FileName\\n    type: string\\n    required: true\\n    description: 需要保存的JSON文件名（会自动添加.json扩展名）\\n  - name: FilePath\\n    type: string\\n    required: true\\n    description: JSON文件保存的目标路径\\n  - name: Content\\n    type: string\\n    required: true\\n    description: 需要处理和保存的包含JSON对象的内容字符串\\noutputs:\\n  - name: WebOutput\\n    type: string\\n    description: 返回操作结果信息，成功时显示保存路径，失败时显示错误信息\\n```\\n\\n运行逻辑\\n\\n- 从输入节点获取文件名、文件路径和内容参数\\n- 清理文件名中的换行符，并确保文件名包含.json扩展名\\n- 构建完整的文件保存路径\\n- 使用正则表达式提取内容中所有{}包围的JSON对象\\n- 对提取的内容进行清理：将多个空格替换为单个空格，将中文标点符号替换为英文标点\\n- 将清理后的字符串转换为Python字典对象\\n- 检查目标文件是否已存在，如果存在则读取现有数据并与新数据合并\\n- 将最终数据序列化为JSON格式，使用UTF-8编码保存到指定文件\\n- 返回操作结果，成功时返回保存信息，异常时返回错误信息'
Outputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': None, 'Id': f'Output{i + 1}', 'name': 'WebOutput', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': None, 'Id': f'Input{i + 1}', 'Isnecessary': True, 'name': 'WebInput', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]

NodeKind = 'Normal'
InputIsAdd = True
OutputIsAdd = False
Label = [{'Id': 'Label1', 'Kind': 'None'}]

# Assign properties to Inputs and Outputs
Inputs[0]['Kind'] = 'String'  # File name
Inputs[0]['name'] = 'FileName'
Inputs[1]['Kind'] = 'String'  # File path
Inputs[1]['name'] = 'FilePath'
Inputs[2]['Kind'] = 'String'  # Content
Inputs[2]['name'] = 'Content'

Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'WebOutput'

def run_node(node):
    # Extract inputs
    file_name = node['Inputs'][0]['Context']
    file_path = node['Inputs'][1]['Context']
    content = node['Inputs'][2]['Context']
    # 去除file_name中的\n
    file_name = file_name.replace('\n','')
    # Ensure the file name has .json extension
    if not file_name.endswith('.json'):
        file_name += '.json'
    
    full_path = os.path.join(file_path, file_name)
    
    # Process content
    try:
        # Regular expression to extract content within {}
        pattern = r'\{[^{}]*\}'
        
        # Extract matches
        matches = re.findall(pattern, content)
        
        # Clean up the extracted strings
        clean_matches = []
        for match in matches:
            clean_match = re.sub(r'\s+', ' ', match)  # Replace any whitespace characters with a single space
            clean_match = clean_match.replace('，', ',').replace('：', ':')  # Replace Chinese punctuation with English punctuation
            clean_matches.append(clean_match)
        
        # Convert to dictionary objects
        new_data = [json.loads(match) for match in clean_matches]
        
        # Check if file exists
        if os.path.exists(full_path):
            # Read existing data
            with open(full_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
            # Append new data to existing data
            existing_data.extend(new_data)
            data = existing_data
        else:
            # Use new data if file does not exist
            data = new_data
        
        # Serialize to JSON
        json_data = json.dumps(data, ensure_ascii=False, indent=4)
        
        # Save JSON to file
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(json_data)
        
        Outputs[0]['Context'] = f"JSON file {file_name} saved at {file_path}"
    except Exception as e:
        Outputs[0]['Context'] = f"Error: {str(e)}"
    
    return Outputs

