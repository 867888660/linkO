import json
import logging
import os
import re
import unicodedata

# === 参数区 =========================================================
OutPutNum = 1
InPutNum  = 2          # ←★ 需要两个输入
NodeKind  = 'Normal'
Lable     = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='**组件功能：**  \n该代码实现了一个节点插入器的功能，能够向一个工作流JSON文件中插入新的节点，并确保节点ID和标签的唯一性。插入的过程包括检查重复的节点ID和标签，确保每个节点的唯一性，最终将更新后的数据保存回文件。\n\n**代码功能摘要：**  \n1. 该代码首先验证输入的文件路径和JSON字符串的有效性。\n2. 它读取并解析目标工作流文件，解析输入的节点JSON。\n3. 新的节点会被添加到工作流的`nodes`数组中，接着对所有节点进行去重处理（包括`id`和`label`）。\n4. 去重完成后，更新的工作流会保存回文件。\n5. 最后，生成操作结果和调试信息作为输出。\n\n**参数：**  \n```yaml\ninputs:\n  - name: File_Path\n    type: string\n    required: true\n    description: 目标工作流JSON文件的路径\n    frozen: true\n  - name: Json\n    type: string\n    required: true\n    description: 要插入的节点的JSON字符串\n    frozen: true\noutputs:\n  - name: Result\n    type: string\n    description: 操作结果信息\n  - name: Debug\n    type: string\n    description: 详细的调试信息输出\n```\n\n**运行逻辑：**  \n- 读取输入：  \n  - 验证文件路径和JSON字符串的有效性。\n  - 如果文件路径无效或JSON字符串为空，抛出相应错误。\n  \n- 数据处理：  \n  - 读取目标工作流文件，检查文件中是否包含`nodes`数组。\n  - 解析输入的节点JSON，支持代码块格式的解析。\n  - 将新的节点数据添加到现有的`nodes`数组。\n\n- 节点去重处理：  \n  - 遍历所有节点，确保每个节点的`id`和`label`在全局范围内唯一。\n  - 如有重复，依次在末尾加上`*`，直到节点不再重复。\n  - 记录所有重命名的操作并输出调试信息。\n\n- 文件保存：  \n  - 将更新后的工作流数据写回到原文件中，采用UTF-8编码并格式化为缩进的JSON格式。\n\n- 生成输出：  \n  - 返回操作结果信息，成功时显示“OK: 现有节点总数 X”，失败时显示相应的错误信息。\n  - 输出完整的调试信息记录，帮助用户了解处理过程。'

# === I/O 描述区 =====================================================
Outputs = [{
    'Num': None, 'Kind': 'String', 'Boolean': False,
    'Id': f'Output{i+1}', 'Context': None,
    'name': f'Result', 'Link': 0, 'Description': ''
} for i in range(OutPutNum)]

Inputs = [{
    'Num': None, 'Kind': 'String_FilePath', 'Id': 'Input1',
    'Context': None, 'Isnecessary': True,  'name': 'File_Path',
    'Link': 0,  'IsLabel': True
},{
    'Num': None, 'Kind': 'String', 'Id': 'Input2',
    'Context': None, 'Isnecessary': True, 'name': 'Json',
    'Link': 0, 'IsLabel': True
}]

# === 工具函数 =======================================================
def _strip_code_fences(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r'^```(?:json)?', '', raw, flags=re.I).strip()
    raw = re.sub(r'```$', '', raw).strip()
    return raw

def _find_json_region(raw: str) -> str:
    raw = _strip_code_fences(raw)
    first = raw.find('{')
    if first == -1:
        raise ValueError('未找到 "{"')
    depth = 0
    in_str, esc = False, False
    for i in range(first, len(raw)):
        ch = raw[i]
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return raw[first:i + 1]
    raise ValueError('大括号不匹配')

def _escape_newlines_inside_strings(js: str) -> str:
    out, in_str, esc = [], False, False
    for ch in js:
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
            elif ch in '\n\r':
                out.append('\\n');  continue
        else:
            if ch == '"':
                in_str = True
        out.append(ch)
    return ''.join(out)

def _basic_clean(text: str) -> str:
    text = unicodedata.normalize('NFC', text)
    return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)

def string_to_json_obj(input_str: str):
    cleaned = _basic_clean(input_str)
    json_part = _find_json_region(cleaned)
    json_part = _escape_newlines_inside_strings(json_part)
    return json.loads(json_part)

def _dedupe_nodes(nodes, debug_list):
    """
    遍历所有节点，保证 id 与 label 全局唯一；
    如有重复，在末尾依次追加 '*' 直到不重复。
    把改名记录写入 debug_list。
    """
    seen_ids, seen_labels = set(), set()
    for n in nodes:
        # ---- id 去重 ----
        orig_id = n.get('id', '')
        new_id  = orig_id or ''
        while new_id in seen_ids:
            new_id += '*'
        if new_id != orig_id:
            debug_list.append(f'id 重名: "{orig_id}" → "{new_id}"')
            n['id'] = new_id
        seen_ids.add(new_id)

        # ---- label 去重 ----
        orig_lb = n.get('label', '')
        new_lb  = orig_lb or ''
        while new_lb in seen_labels:
            new_lb += '*'
        if new_lb != orig_lb:
            debug_list.append(f'label 重名: "{orig_lb}" → "{new_lb}"')
            n['label'] = new_lb
        seen_labels.add(new_lb)

# === 运行核心 =======================================================
def run_node(node):
    debugging = []  # 调试信息
    try:
        # ---------- 1. 读取输入 ----------
        file_path     = node['Inputs'][0]['Context']
        new_node_str  = node['Inputs'][1]['Context']
        debugging.append(f'文件路径: {file_path}')
        debugging.append(f'待插入 Json（前 120 字）: {new_node_str[:120]}...')

        if not file_path or not os.path.isfile(file_path):
            raise FileNotFoundError('File not found.')
        if not new_node_str:
            raise ValueError('Json 字符串为空')

        # ---------- 2. 载入原 workflow ----------
        with open(file_path, 'r', encoding='utf-8') as f:
            workflow = json.load(f)
        if 'nodes' not in workflow or not isinstance(workflow['nodes'], list):
            raise KeyError('目标文件缺少 "nodes" 数组')

        # ---------- 3. 解析新节点 ----------
        new_node_json = string_to_json_obj(new_node_str)
        additions = new_node_json['nodes'] if isinstance(new_node_json, dict) and 'nodes' in new_node_json else [new_node_json]
        workflow['nodes'].extend(additions)

        # ---------- 4. 全局去重 ----------
        _dedupe_nodes(workflow['nodes'], debugging)

        # ---------- 5. 保存 ----------
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(workflow, f, ensure_ascii=False, indent=2)

        msg = f'OK: 现有节点总数 {len(workflow["nodes"])}'
        Outputs[0]['Context'] = msg
        debugging.append(msg)

    except Exception as e:
        err_msg = f'ERROR: {type(e).__name__}: {e}'
        Outputs[0]['Context'] = err_msg
        debugging.append(err_msg)

    # --------- 6. 输出调试 ----------
    logging.info('\n'.join(debugging))
    Outputs.append({'Id': 'Debug', 'Kind': 'String', 'Context': '\n'.join(debugging)})
    return Outputs
