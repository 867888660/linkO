import copy
import os
import logging

# **Define the number of outputs and inputs**
OutPutNum = 1
InPutNum = 1
# **Define the number of outputs and inputs**

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]
NodeKind = 'ArrayTrigger'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='组件功能：这是一个文件夹解析器组件，用于扫描指定文件夹路径下的所有文件，并将文件信息按目录分组整理输出。\\n\\n代码功能摘要：使用os.walk()递归遍历文件夹，将相同目录下的文件归类到字典中，提取文件名（不含扩展名）和完整路径，最终为每个目录生成包含基础路径、文件映射关系和文件夹名称的格式化字符串输出。\\n\\n参数：\\n```yaml\\ninputs:\\n  - name: FilePath\\n    type: string\\n    required: true\\n    description: 需要解析的文件夹路径\\noutputs:\\n  - name: List\\n    type: string\\n    description: 解析后的文件列表，包含每个文件夹的详细信息\\n```\\n\\n运行逻辑：\\n- 接收输入的文件夹路径，首先验证路径是否存在，如果路径不存在则返回错误信息\\n- 使用os.walk()遍历指定路径下的所有文件夹和文件，将相同目录下的文件统一归类到字典中\\n- 提取每个文件的文件名（不含扩展名）和完整路径，并将路径分隔符统一转换为反斜杠\\n- 对每个文件夹生成格式化的字符串输出，包含Basic（文件夹完整路径）、文件名与路径的映射关系、FloderName（当前文件夹名称）\\n- 特殊情况处理：如果路径不存在输出错误信息，如果文件夹为空（没有文件）输出提示信息\\n- 返回包含所有目录文件信息的数组，每个目录对应一个输出项'

# **Assign properties to Inputs**
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'List'

Inputs[0]['Kind'] = 'String_FilePath'
Inputs[0]['name'] = 'FilePath'
# **Assign properties to Inputs**

def run_node(node):
    Array = []
    # 读取输入文件路径
    FilePath = node['Inputs'][0]['Context']
    
    print("文件路径:", FilePath)  # 调试信息，查看文件路径
    # 检查路径是否存在
    if not os.path.exists(FilePath):
        Outputs[0]['Context'] = f"错误: 路径 '{FilePath}' 不存在"
        Array.append(copy.deepcopy(Outputs))
        return Array
    
    # 遍历文件夹及其子文件夹
    file_paths_dict = {}
    for root, dirs, files in os.walk(FilePath):
        for file in files:
            file_path = os.path.join(root, file).replace('/', '\\')
            directory = os.path.dirname(file_path)  # 获取文件所在目录路径
            
            # 将相同目录的文件归类
            if directory not in file_paths_dict:
                file_paths_dict[directory] = []
            
            # 获取不带后缀的文件名
            file_name_without_ext = os.path.splitext(file)[0]
            file_paths_dict[directory].append((file_name_without_ext, file_path))

    # 处理归类后的文件
    file_count = 0
    Array = []
    for directory, file_infos in file_paths_dict.items():
        # 首先添加基础路径
        content = f"Basic：{directory}"
        
        for file_name, file_path in file_infos:
            file_count += 1
            content += f"\n{file_name}：{file_path}"
        
        # 获取文件夹名称
        folder_name = os.path.basename(directory)
        # 添加文件夹名称
        content += f"\nFloderName：{folder_name}"
        
        output_copy = copy.deepcopy(Outputs)
        output_copy[0]['Context'] = content
        Array.append(output_copy)
    
    # 如果没有找到文件，返回提示信息
    if file_count == 0:
        Outputs[0]['Context'] = f"提示: 在路径 '{FilePath}' 中没有找到任何文件"
        Array.append(copy.deepcopy(Outputs))
    
    return Array
