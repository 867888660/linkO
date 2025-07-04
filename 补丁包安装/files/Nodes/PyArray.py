import json
import os
import copy
import hashlib

# === 参数区 =========================================================
OutPutNum = 3          # 输出口数量
InPutNum  = 1          # 输入口数量
NodeKind  = 'ArrayTrigger'
Lable     = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='组件功能：这是一个Python文件遍历处理器，主要用于批量读取指定目录下的Python源代码文件，具有文件变更检测功能。\n\n代码功能摘要：通过SHA256哈希值比对机制，智能识别目录中已修改或新增的Python文件，避免重复处理未变更的文件，实现高效的批量文件内容读取和路径输出。\n\n参数：\\ninputs:\\n  - name: File_Path\\n    type: string\\n    required: true\\n    description: 需要遍历的目录路径\\noutputs:\\n  - name: Py_Code\\n    type: string\\n    description: 读取到的Python文件内容\\n  - name: Py_FilePath\\n    type: string\\n    description: Python文件的完整路径\\n  - name: OutPut3\\n    type: string\\n    description: 调试信息输出\n\n运行逻辑：\\n- 接收目录路径输入并验证路径有效性\\n- 读取目录下的jsonlist.json文件获取已知文件的哈希值映射表\\n- 遍历目录下的所有.py文件（仅一级目录，不包含子目录）\\n- 计算每个Python文件的SHA256哈希值\\n- 将当前哈希值与记录的哈希值进行比较\\n- 只处理哈希值不同或新增的文件，跳过未修改的文件\\n- 读取符合条件的Python文件内容\\n- 为每个处理的文件生成一组输出：文件内容、文件路径和调试信息\\n- 使用深拷贝确保输出数据的独立性\\n- 返回包含所有处理结果的数组'

# === I/O 描述区 =====================================================
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False,
            'Id': f'Output{i + 1}', 'Context': None,
            'name': f'OutPut{i + 1}', 'Link': 0,
            'Description': ''} for i in range(OutPutNum)]

Inputs = [{'Num': None, 'Kind': None,
           'Id': f'Input{i + 1}', 'Context': None,
           'Isnecessary': True, 'name': f'Input{i + 1}',
           'Link': 0, 'IsLabel': True} for i in range(InPutNum)]

# === 针对输入/输出的定制 =============================================
# 第一输入：文件（夹）路径
Inputs[0]['Kind']       = 'String_FilePath'
Inputs[0]['name']       = 'File_Path'
Inputs[0]['Isnecessary'] = True
Inputs[0]['IsLabel']     = True

# 其余输入均默认为字符串
for i in range(1, InPutNum):
    Inputs[i]['Kind'] = 'String'

# 第一个输出：存放读取到的 .py 文件内容
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Py_Code'

Outputs[1]['Kind'] = 'String'
Outputs[1]['name'] = 'Py_FilePath'
# 如果需要调试输出，取消下面两行注释即可
# Outputs.append({'Num': None, 'Kind': 'String', 'Boolean': False,
#                 'Id': 'OutputDebug', 'Context': None,
#                 'name': 'DeBugging', 'Link': 0,
#                 'Description': '调试信息'})

# === 运行逻辑 =======================================================
DEBUG = True  # 切换为 True 可在控制台与第二输出口看到调试信息

def calc_file_hash(filepath):
    """计算文件的SHA256哈希值"""
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def run_node(node):
    """
    遍历指定目录（不深入子目录）下所有 .py 文件，
    逐文件读取内容并输出到 Outputs[0]['String']。
    每个文件对应一组输出，最终返回 Array。
    """
    Array = []

    # —— 获取目录路径（由第 1 输入口传入） ——
    dir_path = node['Inputs'][0]['Context']
    if not dir_path:
        raise ValueError('Input1 (File_Path) 不能为空！')

    if not os.path.isdir(dir_path):
        raise NotADirectoryError(f'指定路径不存在或不是文件夹：{dir_path}')

    # —— 读取jsonlist.json，建立文件名到哈希的映射 ——
    jsonl_path = os.path.join(dir_path, 'jsonlist.json')
    hash_dict = {}
    if os.path.isfile(jsonl_path):
        with open(jsonl_path, 'r', encoding='utf-8') as jf:
            try:
                data = json.load(jf)
                for obj in data:
                    fname = obj.get('Filename')
                    hashv = obj.get('Hash')
                    if fname and hashv:
                        hash_dict[fname] = hashv
            except Exception as e:
                if DEBUG:
                    print(f'调试：读取jsonlist.json失败 → {e}')

    debug_msgs = [] if DEBUG else None
    debug_msgs_dict = {} if DEBUG else None
    # —— 遍历目录下所有 .py 文件（不包含子目录） ——
    py_files = []
    for f in os.listdir(dir_path):
        if f.endswith('.py') and os.path.isfile(os.path.join(dir_path, f)):
            fpath = os.path.join(dir_path, f)
            cur_hash = calc_file_hash(fpath)
            old_hash = hash_dict.get(f)
            file_debug = []
            if DEBUG:
                msg = f"文件 {f} 当前哈希 {cur_hash}，记录哈希 {old_hash}"
                debug_msgs.append(msg)
                file_debug.append(msg)
            if old_hash is None or cur_hash != old_hash:
                if DEBUG:
                    msg = f"文件 {f} 被加入py_files（哈希不一致或无记录）"
                    debug_msgs.append(msg)
                    file_debug.append(msg)
                py_files.append(f)
            else:
                if DEBUG:
                    msg = f"文件 {f} 哈希一致，跳过"
                    debug_msgs.append(msg)
                    file_debug.append(msg)
            if DEBUG:
                debug_msgs_dict[f] = list(file_debug)

    if not py_files and DEBUG:
        print('调试：目录中未找到 .py 文件')

    for fname in py_files:
        fpath = os.path.join(dir_path, fname)

        # 读取文件内容
        try:
            with open(fpath, 'r', encoding='utf-8') as fp:
                py_code = fp.read()
        except Exception as e:
            if DEBUG:
                msg = f"读取 {fname} 失败 → {e}"
                debug_msgs.append(msg)
                if fname in debug_msgs_dict:
                    debug_msgs_dict[fname].append(msg)
                else:
                    debug_msgs_dict[fname] = [msg]
            py_code = f'ERROR: 读取文件失败 - {e}'

        # —— 为当前文件构造输出 —— 
        out_block = copy.deepcopy(Outputs)  # 深拷贝模板
        out_block[0]['Context'] = py_code    # 写入文件内容
        out_block[1]['Context'] = fpath      # 写入文件路径
        if DEBUG and fname in debug_msgs_dict:
            out_block[2]['Context'] = '\n'.join(debug_msgs_dict[fname])
        else:
            out_block[2]['Context'] = ''

        Array.append(out_block)

        if DEBUG:
            msg = f"已处理 {fname}（共 {len(py_files)} 个）"
            debug_msgs.append(msg)
            if fname in debug_msgs_dict:
                debug_msgs_dict[fname].append(msg)
            else:
                debug_msgs_dict[fname] = [msg]

    return Array
