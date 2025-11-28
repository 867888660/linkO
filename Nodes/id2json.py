import json
import logging
import os
import re

# **Function definition**

# **Define the number of outputs and inputs**输入节点与输出节点的数量
OutPutNum = 2
InPutNum = 2
# **Define the number of outputs and inputs**

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]
# **Initialize Outputs and Inputs arrays and assign names directly**
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='根据id解锁对应的json文档并给出输出'
# **Assign properties to Inputs**
for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'
#            节点类别有String,Num,Boolean,String_FilePath
Inputs[0]['Kind'] = 'String_FilePath'
#                 节点名称
Inputs[0]['name'] = 'Json_Path'
#             节点是否需要输入
Inputs[0]['Isnecessary'] = True
#              节点是否是标签
Inputs[0]['IsLabel'] = True
Inputs[1]['Kind'] = 'String'
#                 节点名称
Inputs[1]['name'] = 'Content'
#             节点是否需要输入
Inputs[1]['Isnecessary'] = True

Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Result'

### DeBugging用于解锁调试功能，输出调试信息
Outputs[1]['Kind'] = 'String'
Outputs[1]['name'] = 'SearchAnswer'
###
# **Assign properties to Inputs**
# **Function definition**
def run_node(node):
    file_path   = node['Inputs'][0]['Context']           # .jsonl 路径
    raw_content = node['Inputs'][1]['Context'] or ''     # 含 id=xxx 的文本

    # 1️⃣ 抽取全部 id，去重并保序
    id_list = list(dict.fromkeys(re.findall(r'id\s*=\s*([^\s]+)', raw_content)))
    debug   = [f"提取到 {len(id_list)} 个 id: {id_list}"]

    if not id_list:
        Outputs[0]['Context'] = "[未找到] 输入内容里没有形如 id=xxx 的字段"
        Outputs[1]['Context'] = "\n".join(debug)
        return Outputs

    if not file_path or not os.path.isfile(file_path):
        Outputs[0]['Context'] = f"[错误] 无效文件路径: {file_path}"
        Outputs[1]['Context'] = "\n".join(debug)
        return Outputs

    matched, pending = [], set(id_list)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for ln, line in enumerate(f, 1):
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                _id = data.get('id')
                if _id in pending:
                    matched.append(data)
                    pending.remove(_id)
                    debug.append(f"[行{ln}] 命中 {_id}")
                    if not pending:        # 全部找齐可以提前结束
                        break

        if matched:
            # 多条记录按输入顺序输出
            ordered = [next(d for d in matched if d['id'] == _id) for _id in id_list if any(d['id'] == _id for d in matched)]
            Outputs[0]['Context'] = "\n".join(json.dumps(d, ensure_ascii=False) for d in ordered)
            Outputs[1]['Context'] = "\n".join(debug + ([f"⚠️ 尚未匹配到: {list(pending)}"] if pending else []))
        else:
            Outputs[0]['Context'] = "[未找到] jsonl 中没有任何匹配 id"
            Outputs[1]['Context'] = "\n".join(debug)

    except Exception as e:
        Outputs[0]['Context'] = f"[异常] {e}"
        Outputs[1]['Context'] = "\n".join(debug)

    return Outputs