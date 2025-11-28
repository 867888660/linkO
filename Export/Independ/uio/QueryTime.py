import json
import re
import openpyxl
from datetime import datetime


# **Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 0
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
    #帮我做个时间查询当天时间，格式是XXXX-XX-XX
    total = datetime.now().strftime('%Y-%m-%d')
    Outputs[0]['Context'] = total
    return Outputs

