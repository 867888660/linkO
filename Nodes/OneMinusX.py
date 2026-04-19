import json

# **Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 1
# **Define the number of outputs and inputs

# **Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Kind': None, 'Id': f'Output1{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]
# **Initialize Outputs and Inputs arrays and assign names directly
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# **Assign properties to Inputs
for output in Outputs:
    output['Kind'] = 'Num'

for input in Inputs:
    input['Kind'] = 'Num'
# **Assign properties to Inputs

# **Function definition
def run_node(node):
    x = node['Inputs'][0].get('Num')
    if x is None or x == 0:
        ctx = node['Inputs'][0].get('Context', '')
        try:
            x = float(str(ctx).strip())
        except (ValueError, TypeError):
            x = 0.5
    result = 1 - x
    Outputs[0]['Num'] = result
    Outputs[0]['Context'] = str(result)
    return Outputs
# **Function definition

