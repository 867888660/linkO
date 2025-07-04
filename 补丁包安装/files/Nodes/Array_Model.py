import json
import os
import copy


# **Define the number of outputs and inputs**
OutPutNum = 1
InPutNum = 2
# **Define the number of outputs and inputs**

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]
NodeKind = 'ArrayTrigger'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='组件功能：这是一个数组触发器节点，用于根据指定的数字范围生成包含输出节点序列的数组。\n\n代码功能摘要：接收起始和结束数字作为输入，通过循环遍历指定范围内的每个数字，为每个数字创建一个输出节点的深拷贝并存储到数组中，最终返回包含所有数字序列的数组。\n\n参数：\\n```yaml\\ninputs:\\n  - name: Input1\\n    type: integer\\n    required: true\\n    description: 数字范围的起始值\\n  - name: Input2\\n    type: integer\\n    required: true\\n    description: 数字范围的结束值（包含）\\noutputs:\\n  - name: OutPut1\\n    type: string\\n    description: 生成的数组序列，包含指定范围内所有数字对应的输出节点\\n```\n\n运行逻辑：\\n- 从输入节点获取起始数字Start_Num和结束数字End_Num\\n- 初始化空数组Array用于存储结果\\n- 使用for循环遍历从Start_Num到End_Num+1的范围（包含结束值）\\n- 在每次循环中，将当前数字i赋值给输出节点的Num属性\\n- 对当前输出节点进行深拷贝并添加到Array数组中\\n- 循环结束后返回包含所有数字序列的Array数组\\n- 每个数组元素都是一个完整的输出节点对象，包含对应的数字值'
# **Assign properties to Inputs**
for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'
#            节点类别有String,Num,Boolean,String_FilePath
#Inputs[0]['Kind'] = 'String_FilePath'
#                 节点名称
#Inputs[0]['name'] = 'File_Path'
#             节点是否需要输入
#Inputs[0]['Isnecessary'] = True
#              节点是否是标签
#Inputs[0]['IsLabel'] = True

#Outputs[0]['Kind'] = 'String'
#Outputs[0]['name'] = 'Result'

### DeBugging用于解锁调试功能，输出调试信息
#Outputs[1]['Kind'] = 'String'
#Outputs[1]['name'] = 'DeBugging'
###
# **Assign properties to Inputs**
# **Function definition**

def run_node(node):
    Array = []
    # 读取输入文件路径
    Start_Num = node['Inputs'][0]['Num']
    End_Num = node['Inputs'][1]['Num']
    Count=Start_Num
    #描述遍历条件
    for i in range(Start_Num,End_Num+1):
        Outputs[0]['Num']=i
        Array.append(copy.deepcopy(Outputs))

    return Array
##写出你需要的功能，有需要可以用Debugging输出调试信息，调试信息会在控制台输出，也会在输出节点中输出，方便调试。写出遍历循环的条件，Outputs[i]的输出都可以写明清楚
# **Function definition**
