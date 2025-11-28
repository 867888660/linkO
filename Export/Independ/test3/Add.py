import json

#**Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 2
#**Define the number of outputs and inputs

#**Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Kind': None, 'Id': f'Output1{i + 1}', 'Context': None,'name':f'OutPut{i + 1}','Link':0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True,'name':f'Input{i + 1}','Link':0,'IsLabel':False} for i in range(InPutNum)]
#**Initialize Outputs and Inputs arrays and assign names directly
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]


#**Assign properties to Inputs

for output in Outputs:
    output['Kind'] = 'Num'

for input in Inputs:
    input['Kind'] = 'Num'
#**Assign properties to Inputs

#**Function definition
def run_node(node):
    total = 0
    for i in range(len(node['Inputs'])):
        total += node['Inputs'][i]['Num']
    Outputs[0]['Num'] = total
    print(total)
    return Outputs
#**Function definition