import json
import http.client
#**Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 0
#**Define the number of outputs and inputs

#**Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Kind': None,'Boolean':False, 'Id': f'Output{i + 1}', 'Context': None,'name':f'OutPut{i + 1}','Link':0,'Description':''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True,'name':f'Input{i + 1}','Link':0,'IsLabel':False} for i in range(InPutNum)]
#**Initialize Outputs and Inputs arrays and assign names directly
NodeKind = 'IfNode'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]


#**Assign properties to Inputs

for output in Outputs:
    output['Kind'] = 'Trigger'

for input in Inputs:
    input['Kind'] = 'String'
#**Assign properties to Inputs

#**Function definition
def run_node(node):
    Outputs.clear()
    for i in range(len(node['Outputs'])):
        Outputs.append(node['Outputs'][i])
        Outputs[i]['Boolean'] = False
    #print('Out阿松大',Outputs)
    for i, output in enumerate(Outputs):
        if output.get('selectKind') == 'String' and output.get('selectNum') is not None:
            input_value = node['Inputs'][output['selectNum']]['Context']
            # 检查是否不包含 selectBox3 的值
            if output['selectBox2'] == 'exclude' and output['selectBox3'] is not None:
                if output['selectBox3'] not in input_value:
                    # 执行当 input_value 不包含 selectBox3 的值时的操作
                    print("Does not include the specified value.")
                    output['Boolean'] = True

            # 检查 input_value 是否为空
            if output['selectBox2'] == 'empty' and output['selectBox3'] is not None:
                if input_value == '':
                    # 执行当 input_value 为空的操作
                    print("Value is empty.")
                    output['Boolean'] = True
            # 检查 input_value 是否不为空
            if output['selectBox2'] == 'not empty' and output['selectBox3'] is not None:
                if input_value != '':
                    # 执行当 input_value 不为空的操作
                    print("Value is not empty.")
                    output['Boolean'] = True
            # 检查是否包含 selectBox3 的值
            print('测试',output['selectBox2'],output['selectBox3'],input_value)
            if output['selectBox2'] == 'include' and output['selectBox3'] is not None:
                print('input_value',output['selectBox3'],input_value)
                if output['selectBox3'] in input_value:
                    # 执行当 input_value 包含 selectBox3 的值时的操作
                    print("Includes the specified value.")
                    output['Boolean'] = True
                #检查是否包含
        if output.get('selectKind') == 'Num' and output.get('selectNum') is not None:
            input_value = node['Inputs'][output['selectNum']]['Num']
            if output['selectBox2'] == '>':
                if input_value > int(output['selectBox3']):
                    output['Boolean'] = True
            if output['selectBox2'] == '<':
                if input_value < int(output['selectBox3']):
                    output['Boolean'] = True
            if output['selectBox2'] == '==':
                if input_value == int(output['selectBox3']):
                    output['Boolean'] = True
            if output['selectBox2'] == '!=':
                if input_value != int(output['selectBox3']):
                    output['Boolean'] = True
            if output['selectBox2'] == '>=':
                if input_value >= int(output['selectBox3']):
                    output['Boolean'] = True
            if output['selectBox2'] == '<=':
                if input_value <= int(output['selectBox3']):
                    output['Boolean'] = True
        #print('input_argsdas1大',output.get('Kind'),output.get('selectNum'),input_args)
        if output.get('selectKind') == 'Boolean' and output.get('selectNum') is not None:
            #print('啊实打实VS地方',input_args[output['selectNum']],output['selectBox2'])
            if output['selectBox2'] == 'true':
                if node['Inputs'][output['selectNum']]['Boolean'] == True:
                    output['Boolean'] = True
            if output['selectBox2'] == 'false' :
                if node['Inputs'][output['selectNum']]['Boolean']  == False:
                    output['Boolean'] = True
        output['Kind'] = 'Boolean'
    #print(Outputs,input_args)

    return Outputs
#**Function definition