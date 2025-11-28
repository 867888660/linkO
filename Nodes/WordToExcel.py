import json
import http.client
import requests
import re
import copy
import chardet

# **Define the number of outputs and inputs**
OutPutNum = 3
FunctionIntroduction='这是一个文本分割处理组件，专门用于将包含多个问答对的文本文件按\"答案\"关键词进行分割处理。\\n\\n组件功能：读取指定的文本文件，自动检测文件编码，使用正则表达式按\"答案\"关键词将文本分割成多个独立的问答对片段，并为每个片段提供详细的处理状态信息。\\n\\n代码功能摘要：程序首先使用chardet库检测文件编码确保正确读取，然后通过正则表达式re.split()按\"答案\"关键词分割文本内容，将问题和对应答案重新组合成完整的问答对，最后为每个片段生成包含内容、序号和结束标记的输出对象数组。\\n\\n参数：\\n```yaml\\ninputs:\\n  - name: Input1\\n    type: file\\n    required: true\\n    description: 要处理的文本文件路径\\noutputs:\\n  - name: context\\n    type: string\\n    description: 分割后的问答对文本内容\\n  - name: num\\n    type: integer\\n    description: 当前处理片段的序号\\n  - name: Is_Last\\n    type: boolean\\n    description: 标记是否为最后一个片段\\n```\\n\\n运行逻辑：\\n- 读取输入的文件路径参数\\n- 使用chardet库读取文件前1000字节检测文件编码格式\\n- 根据检测到的编码格式完整读取文件内容\\n- 使用正则表达式re.split()按\"答案\"关键词分割文本内容\\n- 将分割后的内容重新组合，确保每个片段包含完整的问题和对应答案\\n- 遍历所有分割后的片段，为每个片段创建输出对象\\n- 将片段内容存储到context输出，记录序号到num输出\\n- 判断是否为最后一个片段并设置Is_Last标记\\n- 使用深拷贝将每个输出对象添加到结果数组中\\n- 返回包含所有处理结果的数组供后续节点使用'
InPutNum = 1
# **Define the number of outputs and inputs**

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]
NodeKind = 'ArrayTrigger'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# **Assign properties to Inputs**
Outputs[0]['Kind'] = 'String'
Outputs[1]['Kind'] = 'Num'
Outputs[0]['name'] = 'context'
Outputs[1]['name'] = 'num'
Outputs[2]['name'] = 'Is_Last'
Outputs[2]['Kind'] = 'Boolean'
for input in Inputs:
    input['Kind'] = 'String_FilePath'
# **Assign properties to Inputs**

# **Function definition**
def run_node(node):
    Array = []

    # 读取输入文件路径
    file_path = node['Inputs'][0]['Context']
    print("文件路径:", file_path)  # 调试信息，查看文件路径
    try:
        # 先读取部分内容以检测编码
        with open(file_path, 'rb') as file:
            raw_data = file.read(1000)  # 读取前1000字节
            result = chardet.detect(raw_data)
            encoding = result['encoding']
            print("检测到的编码:", encoding)

        # 使用检测到的编码读取文件内容
        def split_content_by_answer(file_path, encoding):
            with open(file_path, 'r', encoding=encoding) as file:
                content = file.read()
                print("文件内容:\n", content)  # 调试信息，查看文件内容
                
                # 正则表达式匹配，以“答案”开始，分割前后的内容
                # 按照 "答案" 行进行分割，保留每个段落及其答案
                events = re.split(r'(答案\S*)', content.strip())  
                
                # 重新组合问题和对应答案
                split_events = []
                for i in range(0, len(events)-1, 2):
                    question = events[i].strip()
                    answer = events[i+1].strip()
                    split_events.append(f"{question}\n{answer}")
                
                print("分割后的事件:\n", split_events)  # 调试信息，查看分割后的事件
                return split_events

        events = split_content_by_answer(file_path, encoding)

        # 存储事件到输出节点
        for event in events:
            try:
                # 更新上下文
                Outputs[0]['Context'] = event

                # 这个数组的序号
                Outputs[1]['Num'] = len(Array)  # 记录当前事件在数组中的位置
                Outputs[2]['Boolean'] = False  # 是否是最后一个事件
                if Outputs[1]['Num'] == len(events) - 1:
                    Outputs[2]['Boolean'] = True
                

                # 添加独立的输出对象
                Array.append(copy.deepcopy(Outputs))  # 使用 deep copy 来避免引用问题
            except Exception as e:
                print(f"Error processing event: {e}")

    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

    # 返回 Array
    print('分割后的事件数组:', Array)
    return Array
# **Function definition**
