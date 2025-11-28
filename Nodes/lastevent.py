import json
import chardet

# Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 1

# Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': 'Output1', 'name': 'WebOutput', 'Link': 0}]
Inputs = [{'Num': None, 'Context': None, 'Boolean': False, 'Kind': 'String', 'Id': 'Input1', 'Isnecessary': True, 'name': 'WebInput', 'Link': 0, 'IsLabel': False}]
FunctionIntroduction='组件功能：这是一个文本文件读取和内容提取组件，主要用于读取文件并提取其中最后一段被特定分隔符分隔的内容。\\n\\n代码功能摘要：使用chardet库自动检测文件编码，读取文件内容后查找\'*^*\'分隔符，提取最后一个分隔符后的文本内容，如遇异常则返回错误信息。\\n\\n参数：\\n```yaml\\ninputs:\\n  - name: WebInput\\n    type: file\\n    required: true\\n    description: 需要读取和解析的文件路径\\noutputs:\\n  - name: WebOutput\\n    type: string\\n    description: 提取的文本内容或错误信息\\n```\\n\\n运行逻辑：\\n- 从输入节点获取文件路径参数\\n- 使用二进制模式打开文件，读取原始数据\\n- 通过chardet库自动检测文件的字符编码格式\\n- 使用检测到的编码格式重新打开文件并读取全部内容\\n- 在文件内容中搜索\'*^*\'分隔符\\n- 如果找到分隔符，使用split方法分割内容并取最后一段，去除首尾空白字符\\n- 如果未找到分隔符，设置输出为空字符串\\n- 如果在文件处理过程中发生任何异常（文件不存在、编码错误等），捕获异常并将错误信息转换为字符串作为输出\\n- 将处理结果存储到输出节点并返回'
NodeKind = 'Normal'
InputIsAdd = False
OutputIsAdd = False
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# Assign properties to Inputs and Outputs
for output in Outputs:
    output['Kind'] = 'String'
    output['name'] = 'OutputText'

for input in Inputs:
    input['Kind'] = 'String_FilePath'
    input['Isnecessary'] = True
    input['name'] = 'FilePath'

# Function definition
def run_node(node):
    file_path = node['Inputs'][0]['Context']
    try:
        # Detect file encoding
        with open(file_path, 'rb') as file:
            raw_data = file.read()
            result = chardet.detect(raw_data)
            encoding = result['encoding']
        
        # Read file with detected encoding
        with open(file_path, 'r', encoding=encoding) as file:
            content = file.read()
        
        if '*^*' in content:
            last_part = content.split('*^*')[-1].strip()
            Outputs[0]['Context'] = last_part
        else:
            Outputs[0]['Context'] = ''
    except Exception as e:
        Outputs[0]['Context'] = str(e)
    return Outputs
