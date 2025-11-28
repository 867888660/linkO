import json
import logging
import os
import re

# **Function definition**

# **Define the number of outputs and inputs**输入节点与输出节点的数量
OutPutNum = 1
InPutNum = 1
# **Define the number of outputs and inputs**

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]
# **Initialize Outputs and Inputs arrays and assign names directly**
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='组件功能（简述代码整体功能）\\\\n\\\\n根据输入的字数计算对应的分数，实现字数与分数的映射转换。\\\\n\\\\n代码功能摘要（概括核心算法或主要处理步骤）\\\\n\\\\n采用分段计分规则：字数大于等于930分得10分，530-929字数区间按每50字为一个计分单位递减，少于530字得2分。通过整数转换和条件判断实现字数到分数的精确映射。\\\\n\\\\n参数\\\\n\\\\n```yaml\\\\ninputs:\\\\n  - name: Input1\\\\n    type: string\\\\n    required: true\\\\n    description: 需要计算分数的字数\\\\noutputs:\\\\n  - name: OutPut1\\\\n    type: string\\\\n    description: 根据字数计算得出的分数\\\\n```\\\\n\\\\n运行逻辑\\\\n\\\\n- 接收输入的字数参数并尝试转换为整数类型\\\\n- 判断字数是否大于等于930，如果是则直接赋予10分\\\\n- 判断字数是否在530-929区间内，如果是则计算缺少的50字块数量\\\\n- 根据缺少的块数从10分中扣除相应分数得到最终得分\\\\n- 如果字数少于530则直接赋予2分\\\\n- 处理输入格式错误的情况，返回错误提示信息\\\\n- 将计算结果存储到输出节点并返回'
# **Assign properties to Inputs**
for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'
# **Assign properties to Inputs**
# **Function definition**

def run_node(node):
    WordsNum = node['Inputs'][0]['Context']
    Soccer = ""
    Debugging = []
    
    try:
        # Convert input to integer
        word_count = int(WordsNum)
        
        # Apply scoring rules
        if word_count >= 930:
            Soccer = "10"
        elif word_count >= 530:
            # Calculate how many 50-word blocks are missing from 930
            missing_blocks = (930 - word_count) // 50
            if (930 - word_count) % 50 > 0:  # If there's a remainder, count it as a full block
                missing_blocks += 1
            score = 10 - missing_blocks
            Soccer = str(score)
        else:
            Soccer = "2"
            
    except ValueError:
        Soccer = "输入必须是数字"
    
    Outputs[0]['Context'] = Soccer
    return Outputs
# **Function definition**
