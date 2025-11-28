import json
import http.client
import requests
import re
import copy
import chardet
import logging
import os

# **Define the number of outputs and inputs**
OutPutNum = 1
InPutNum = 2
# **Define the number of outputs and inputs**

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]
NodeKind = 'ArrayTrigger'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个数组触发器组件，用于生成指定范围内的连续数字序列，为后续节点提供批量的数值输入。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n通过接收起始和结束数字参数，使用for循环遍历指定范围内的每个整数，将每个数字封装成输出节点对象并存储到数组中，最终返回包含完整数字序列的数组。\\n\\n参数\\n```yaml\\ninputs:\\n  - name: Start_Num\\n    type: number\\n    required: true\\n    description: 数字序列的起始值\\n  - name: End_Num\\n    type: number\\n    required: true\\n    description: 数字序列的结束值（包含在序列中）\\noutputs:\\n  - name: Num\\n    type: number\\n    description: 生成的数字序列中的每个数字值\\n```\\n\\n运行逻辑（用 - 列表描写详细流程）\\n- 从输入节点获取起始数字Start_Num和结束数字End_Num\\n- 初始化空数组Array用于存储生成的数字序列\\n- 使用for循环遍历从Start_Num到End_Num（包含端点）的每个整数\\n- 在每次循环中，将当前数字i赋值给输出节点的Num属性\\n- 使用深拷贝将当前输出状态保存到Array数组中，确保每个数组元素都是独立的输出节点对象\\n- 循环结束后返回包含完整数字序列的Array数组\\n- 返回的数组可供后续节点进行批量处理或循环操作'

# **Assign properties to Inputs**
Outputs[0]['Kind'] = 'Num'
Outputs[0]['name'] = 'Num'

Inputs[0]['Kind'] = 'Num'
Inputs[0]['name'] = 'Start_Num'
Inputs[1]['Kind'] = 'Num'
Inputs[1]['name'] = 'End_Num'
# **Assign properties to Inputs**

def run_node(node):
    Array = []
    # 读取输入文件路径
    Start_Num = node['Inputs'][0]['Num']
    End_Num = node['Inputs'][1]['Num']
    Count=Start_Num
    for i in range(Start_Num,End_Num+1):
        Outputs[0]['Num']=i
        Array.append(copy.deepcopy(Outputs))

    return Array
