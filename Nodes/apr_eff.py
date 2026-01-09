import json
import logging
import os
import re
import math

# **Function definition**

# **Define the number of outputs and inputs**输入节点与输出节点的数量
OutPutNum = 1
InPutNum = 2
# **Define the number of outputs and inputs**

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]
# **Initialize Outputs and Inputs arrays and assign names directly**
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个年化收益率计算组件，用于根据投资回报率和剩余天数计算有效年化收益率（APR）。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n程序接收两个输入参数：投资回报率（roi_if_win）和剩余天数（days_to_end），通过复利计算公式将短期收益率转换为年化收益率。计算公式为：apr_eff_if_win = (1 + roi_if_win)^(365/days_to_end) - 1。\\n\\n参数\\n```yaml\\ninputs:\\n  - name: days_to_end\\n    type: number\\n    required: true\\n    description: 距离结束的天数\\n  - name: roi_if_win\\n    type: number\\n    required: true\\n    description: 如果获胜的投资回报率（ROI）\\noutputs:\\n  - name: apr_eff_if_win\\n    type: number\\n    description: 有效年化收益率（APR）\\n```\\n\\n运行逻辑（用 - 列表描写详细流程）\\n- 程序启动时定义输入输出节点数量，设置为2个输入和1个输出\\n- 初始化输入输出数组，为每个节点分配基础属性包括ID、名称、类型等\\n- 配置节点类型为Normal，设置标签属性Label1\\n- 设置输入节点days_to_end和roi_if_win的数据类型为Num（数字）\\n- 设置输出节点apr_eff_if_win的数据类型为Num（数字）\\n- 执行run_node函数时从输入节点获取days_to_end和roi_if_win的数值\\n- 验证输入数据的有效性，确保days_to_end大于0且roi_if_win不为None\\n- 使用年化计算公式：apr_eff_if_win = (1 + roi_if_win)^(365/days_to_end) - 1\\n- 将计算结果赋值给输出节点的Context属性\\n- 返回包含处理结果的Outputs数组'
# **Assign properties to Inputs**
# 设置输入节点属性
Inputs[0]['Kind'] = 'String'
Inputs[0]['name'] = 'days_to_end'

Inputs[1]['Kind'] = 'String'
Inputs[1]['name'] = 'roi_if_win'

# 设置输出节点属性
Outputs[0]['Kind'] = 'Num'
Outputs[0]['name'] = 'apr_eff_if_win'
#            节点类别有String,Num,Boolean,String_FilePath
#                 节点名称
#             节点是否需要输入
#              节点是否是标签

### DeBugging用于解锁调试功能，输出调试信息
#Outputs[1]['Kind'] = 'String'
#Outputs[1]['name'] = 'DeBugging'
###
# **Assign properties to Inputs**
# **Function definition**
def run_node(node):
    # 获取输入数据
    def _get_as_float(input_item):
        """兼容 Num/String 两种端口：优先读 Num，其次读 Context。"""
        if not isinstance(input_item, dict):
            return None
        v = input_item.get('Num')
        if v is None:
            v = input_item.get('Context')
        if v is None:
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    days_to_end = _get_as_float((node.get('Inputs') or [{}, {}])[0])
    roi_if_win = _get_as_float((node.get('Inputs') or [{}, {}])[1])
    
    Debugging = []
    
    # 验证输入数据
    if days_to_end is None or roi_if_win is None:
        Debugging.append("错误：输入数据不能为空")
        Outputs[0]['Num'] = None
        Outputs[0]['Context'] = ""
        return Outputs
    
    try:
        # 验证days_to_end必须大于0
        if days_to_end <= 0:
            Debugging.append(f"错误：days_to_end必须大于0，当前值为{days_to_end}")
            Outputs[0]['Num'] = None
            Outputs[0]['Context'] = ""
            return Outputs
        
        # 计算年化收益率
        # 公式：apr_eff_if_win = (1 + roi_if_win)^(365/days_to_end) - 1
        base = 1 + roi_if_win
        exponent = 365.0 / days_to_end
        apr_eff_if_win = math.pow(base, exponent) - 1
        
        Debugging.append(f"输入：days_to_end={days_to_end}, roi_if_win={roi_if_win}")
        Debugging.append(f"计算：base={base}, exponent={exponent}")
        Debugging.append(f"输出：apr_eff_if_win={apr_eff_if_win}")
        
        # 端口为 Num：写入 Num；同时写入 Context 字符串，方便历史/跨类型转换兜底
        Outputs[0]['Num'] = apr_eff_if_win
        Outputs[0]['Context'] = str(apr_eff_if_win)
        
    except (ValueError, TypeError) as e:
        Debugging.append(f"错误：输入数据格式不正确 - {str(e)}")
        Outputs[0]['Num'] = None
        Outputs[0]['Context'] = ""
    except Exception as e:
        Debugging.append(f"错误：计算过程中发生异常 - {str(e)}")
        Outputs[0]['Num'] = None
        Outputs[0]['Context'] = ""
    
    return Outputs
##写出你需要的功能，有需要可以用Debugging输出调试信息，调试信息会在控制台输出，也会在输出节点中输出，方便调试。
# **Function definition**

