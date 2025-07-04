import json
import http.client
#**Define the number of outputs and inputsfasdfs大1.09
OutPutNum = 1
InPutNum = 0
#**Define the number of outputs and inputs

#**Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Kind': None,'Boolean':False, 'Id': f'Output{i + 1}', 'Context': None,'name':f'OutPut{i + 1}','Link':0,'Description':''} for i in range(OutPutNum)]
FunctionIntroduction='组件功能：这是一个条件判断节点，用于根据配置的多个判断条件对输入参数进行逻辑判断，并输出布尔值结果。\\n\\n代码功能摘要：该节点支持对String、Number、Boolean三种类型的输入参数进行多条件判断，通过配置判断主体、条件操作符和目标值，实现复杂的业务规则判断。支持And/Or两种逻辑组合方式，可以灵活处理多个条件的组合判断。\\n\\n参数：\\n```yaml\\ninputs: []\\noutputs:\\n  - name: OutPut1\\n    type: boolean\\n    description: 条件判断的最终结果，true表示条件满足，false表示条件不满足\\n```\\n\\n运行逻辑：\\n- 清空并重新初始化输出数组，将所有输出的Boolean值设为False\\n- 遍历每个输出节点，提取其配置的判断条件参数：IfLogicSubjectArray（判断主体数组）、IfLogicConditionArray（判断条件数组）、IfLogicContentArray（判断内容数组）、IfLogicKind（逻辑组合方式）\\n- 对每组判断条件进行并行处理，根据最小数组长度确定实际处理的条件数量\\n- 对于每个判断条件，根据Subject名称在输入数组中查找对应的输入参数\\n- 根据输入参数的类型执行相应的判断逻辑：String类型支持include/exclude/empty/not empty判断；Number类型支持>/</==/!=/>=/<= 数值比较；Boolean类型支持true/false判断\\n- 收集所有单个条件的判断结果到multi_results数组中\\n- 根据IfLogicKind的值进行最终结果计算：\'And\'模式下所有条件都为true时结果才为true；\'Or\'模式下任一条件为true时结果就为true\\n- 将最终判断结果赋值给输出的Boolean字段，并设置输出类型为Boolean\\n- 返回处理完成的输出数组'
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

    for i, output in enumerate(Outputs):
        # 基本调试信息
        print(f"\n[DEBUG] ==== 处理 Outputs[{i}] ====")
        print(f"[DEBUG] 原始 output：{output}")

        IfLogicConditionArray = output.get('IfLogicConditionArray') or []
        IfLogicSubjectArray   = output.get('IfLogicSubjectArray')   or []
        IfLogicContentArray   = output.get('IfLogicContentArray')   or []
        IfLogicKind           = output.get('IfLogicKind')           or 'And'

        print(f"[DEBUG] IfLogicSubjectArray   = {IfLogicSubjectArray}")
        print(f"[DEBUG] IfLogicConditionArray = {IfLogicConditionArray}")
        print(f"[DEBUG] IfLogicContentArray   = {IfLogicContentArray}")
        print(f"[DEBUG] IfLogicKind           = {IfLogicKind}")

        # 旧的单条逻辑兼容（如有需要，也可打印内部变量）
        # …（此处保持你的原有 String/Num/Boolean 判定代码）…

        # === NEW: 并行多条逻辑判定 with debug prints ===
        multi_results = []
        if IfLogicConditionArray and IfLogicSubjectArray:
            min_len = min(
                len(IfLogicSubjectArray),
                len(IfLogicConditionArray),
                len(IfLogicContentArray)
            )
            # 然后用这个长度来循环
            for idx in range(min_len):
                subj = IfLogicSubjectArray[idx]
                cond = IfLogicConditionArray[idx]
                cont = IfLogicContentArray[idx] if idx < len(IfLogicContentArray) else None

                print(f"\n[DEBUG] -- 规则 {idx} --")
                print(f"[DEBUG]   Subject = {subj}")
                print(f"[DEBUG]   Condition = {cond}")
                print(f"[DEBUG]   Content = {cont}")

                # 查找对应 input 索引和类型
                sel_num = None
                sel_kind = None
                for j, inp in enumerate(node['Inputs']):
                    print(f"[DEBUG] {j}  检查 Input {subj}，name = {inp.get('name')}")
                    if inp.get('name') == subj:
                        sel_num = j
                        sel_kind = inp.get('Kind')
                        print(f"[DEBUG]   找到对应 Input {j}, Kind = {sel_kind}")
                        break

                print(f"[DEBUG]   找到 selectNum = {sel_num}, selectKind = {sel_kind}")

                if sel_num is None:
                    print(f"[DEBUG]   没有匹配到输入，结果视为 False")
                    multi_results.append(False)
                    continue

                # 执行判定
                result = False
                if sel_kind == 'String':
                    print(f"[DEBUG]   执行 String 判定{sel_num}")
                    input_val = node['Inputs'][sel_num].get('Context', '')
                    print(f"[DEBUG]   输入值 = {input_val}")
                    if cond == 'include':
                        result = (cont in input_val)
                    elif cond == 'exclude':
                        result = (cont not in input_val)
                    elif cond == 'Eempty':
                        result = (input_val == '')
                    elif cond == 'not empty':
                        result = (input_val != '')
                elif sel_kind == 'Num':
                    input_val = node['Inputs'][sel_num].get('Num', 0)
                    try:
                        num_cont = int(cont)
                    except Exception as e:
                        print(f"[DEBUG]   转换 Content 到 int 失败：{e}")
                        num_cont = 0
                    if cond == '>':
                        result = input_val > num_cont
                    elif cond == '<':
                        result = input_val < num_cont
                    elif cond == '==':
                        result = input_val == num_cont
                    elif cond == '!=':
                        result = input_val != num_cont
                    elif cond == '>=':
                        result = input_val >= num_cont
                    elif cond == '<=':
                        result = input_val <= num_cont
                    print(f"[DEBUG]   输入值 = {input_val}, 条件值 = {num_cont}, 结果 = {result}")
                elif sel_kind == 'Boolean':
                    input_val = node['Inputs'][sel_num].get('Boolean', False)
                    if cond == 'true':
                        result = (input_val is True)
                    elif cond == 'false':
                        result = (input_val is False)

                print(f"[DEBUG]   规则 {idx} 判定结果 = {result}")
                multi_results.append(result)

            print(f"\n[DEBUG] all multi_results = {multi_results}")
            if IfLogicKind == 'And':
                final_bool = all(multi_results)
            else:  # Or
                final_bool = any(multi_results)
            print(f"[DEBUG] 汇总 IfLogicKind='{IfLogicKind}' => {final_bool}")
            output['Boolean'] = final_bool

        # 结束
        output['Kind'] = 'Boolean'
        print(f"[DEBUG] 最终 output['Boolean'] = {output['Boolean']}")

    return Outputs
