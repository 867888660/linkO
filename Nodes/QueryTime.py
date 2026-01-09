import json
import re
import openpyxl
from datetime import datetime, timezone


# **Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 0
FunctionIntroduction='组件功能：这是一个获取当前UTC时间的功能组件，用于输出格式化的当前世界时（UTC）。\\n\\n代码功能摘要：使用Python的datetime模块获取当前UTC时间，并通过strftime方法将其格式化为\"YYYY-MM-DDTHH:MM:SSZ\"格式的时间字符串输出。\\n\\n参数：\\n```yaml\\ninputs: []\\noutputs:\\n  - name: OutPut1\\n    type: string\\n    description: 格式为\"YYYY-MM-DDTHH:MM:SSZ\"的当前UTC时间字符串\\n```\\n\\n运行逻辑：\\n- 调用datetime.now(timezone.utc)方法获取当前UTC时间\\n- 使用strftime(\'%Y-%m-%dT%H:%M:%SZ\')方法将时间对象格式化为\"YYYY-MM-DDTHH:MM:SSZ\"格式的字符串\\n- 将格式化后的时间字符串赋值给Outputs[0][\'Context\']作为输出结果\\n- 返回包含当前UTC时间的Outputs数组'
# **Define the number of outputs and inputs

# **Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Kind': None, 'Id': f'Output1{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]
# **Initialize Outputs and Inputs arrays and assign names directly
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# **Assign properties to Inputs
for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'
# **Assign properties to Inputs

# **Function definition
def run_node(node):
    total = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    Outputs[0]['Context'] = total
    return Outputs

