#**Define the number of outputs and inputs
OutPutNum = 0
InPutNum = 0
#**Define the number of outputs and inputs

#**Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Kind': 'AnchorContext', 'Id': f'Output{i + 1}', 'Context': None,'name':f'OutPut{i + 1}','IsLabel':False,'Link':0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind':'Anchor', 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True,'name':f'Input{i + 1}','Link':0} for i in range(InPutNum)]
#**Initialize Outputs and Inputs arrays and assign names directly
NodeKind = 'Normal'
#**Assign properties to Inputs
for output in Outputs:
    output['Kind'] = 'AnchorContext'

for input in Inputs:
    input['Kind'] = 'AnchorNum'

Outputs[0]['Context'] = '你相信自由意志吗！'
#**Assign properties to Inputs


#**Function definition
def run_node(input_args):
    # 根据输入名称更新 Inputs 数组

    return Outputs
#**Function definition
