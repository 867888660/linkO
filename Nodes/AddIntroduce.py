import json
import logging
import os
import re

# === I/O 参数区 =====================================================
OutPutNum = 1
InPutNum  = 2                         # 两个输入：File_Path 和 Introduce

FunctionIntroduction='组件功能\\n将给定的介绍文本更新到指定Python文件的FunctionIntroduction变量中，支持单行和多行文本的安全处理。\\n\\n代码功能摘要\\n通过文件IO和正则表达式，定位并替换Python文件中的FunctionIntroduction变量赋值。对输入文本进行预处理和转义，确保多行文本的正确存储。支持处理单行赋值和多行区块赋值两种情况。\\n\\ninputs:\\n  - name: File_Path\\n    type: string\\n    required: true\\n    description: 需要修改的Python文件的完整路径\\n  - name: Introduce\\n    type: string\\n    required: true\\n    description: 新的介绍文本内容\\n\\noutputs:\\n  - name: Result\\n    type: string\\n    description: 操作执行结果和详细调试信息\\n\\n运行逻辑\\n- 验证输入的文件路径是否存在且有效\\n- 对输入的介绍文本进行预处理：\\n  - 统一各种换行符为\\\\n\\n  - 使用json.dumps进行安全转义\\n  - 处理单引号的转义\\n- 读取目标Python文件的所有内容\\n- 使用正则表达式查找FunctionIntroduction变量的赋值位置\\n- 如果找到现有赋值：\\n  - 判断是否为多行区块赋值(带括号)\\n  - 删除旧的赋值内容（可能跨多行）\\n  - 在原位置插入新的赋值语句\\n- 如果未找到现有赋值：\\n  - 在第10行位置插入新的赋值语句\\n- 将修改后的内容写回原文件\\n- 返回包含执行状态和调试信息的结果字符串'

Outputs = [{
    'Num': None, 'Kind': 'String', 'Boolean': False,
    'Id': f'Output{i + 1}', 'Context': None,
    'name': 'Result', 'Link': 0, 'Description': ''
} for i in range(OutPutNum)]

Inputs = [{
    'Num': None, 'Kind': 'String_FilePath', 'Id': 'Input1',
    'Context': None, 'Isnecessary': True,  'name': 'File_Path',
    'Link': 0,  'IsLabel': True
}, {
    'Num': None, 'Kind': 'String', 'Id': 'Input2',
    'Context': None, 'Isnecessary': True, 'name': 'Introduce',
    'Link': 0,  'IsLabel': False
}]

NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
# ===================================================================


def _sanitize_introduce(raw: str) -> str:
    """
    将多行文本所有换行 -> 字面 '\n'，同时仅转义单引号。
    使用 json.dumps 让 JSON 帮我们完成安全、一次性的转义，
    避免出现 \\n 这种“二次转义”。
    """
    # 1. 统一换行
    raw = raw.replace('\r\n', '\n').replace('\r', '\n')
    # 2. json.dumps 会把真实换行 → \n，并对其它特殊字符做合法转义
    dumped = json.dumps(raw, ensure_ascii=False)   # '"行 1\n行 2"'  (带双引号)
    dumped = dumped[1:-1]                          # 去掉首尾双引号
    # 3. 由于最终要放在单引号包裹的字符串里，需要把单引号再转义一次
    return dumped.replace("'", "\\'")


def run_node(node):
    """
    主执行函数
    """
    file_path = node['Inputs'][0]['Context']
    introduce_raw = node['Inputs'][1]['Context']
    debugging = []

    try:
        # —— 校验文件路径 ————————————————————————————————
        if not file_path or not os.path.isfile(file_path):
            raise FileNotFoundError(f'找不到文件: {file_path}')

        # —— 生成新的单行赋值 ——————————————————————————
        sanitized = _sanitize_introduce(introduce_raw)
        new_line = f"FunctionIntroduction='{sanitized}'\n"

        # —— 读取原文件 ————————————————————————————————
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # —— 查找并替换旧的赋值（支持多行区块） —————————
        start_pat = re.compile(r'^\s*FunctionIntroduction\s*=')
        replaced = False

        for i, line in enumerate(lines):
            if start_pat.match(line):
                # 判断是否是多行拼接 (  ...  )
                if '(' in line and ')' not in line:
                    # 找到对应的右括号所在行
                    end_idx = i
                    for j in range(i + 1, len(lines)):
                        if lines[j].strip().endswith(')'):
                            end_idx = j
                            break
                    del lines[i:end_idx + 1]
                    debugging.append(f'删除旧区块：第 {i + 1} 行 - 第 {end_idx + 1} 行')
                else:
                    del lines[i]
                    debugging.append(f'删除旧赋值：第 {i + 1} 行')

                lines.insert(i, new_line)
                debugging.append(f'插入新赋值：第 {i + 1} 行')
                replaced = True
                break

        # —— 未找到旧赋值：默认插入到第 10 行 ————————————
        if not replaced:
            insert_idx = 9  # 第 10 行，0‑based
            while len(lines) < insert_idx:
                lines.append('\n')
            lines.insert(insert_idx, new_line)
            debugging.append('未找到旧赋值，已在第 10 行插入新赋值')

        # —— 写回文件 ————————————————————————————————
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        result = 'OK: 更新完成'

    except Exception as e:
        logging.exception(e)
        result = f'Error: {e}'
        debugging.append(result)

    # —— 返回状态与调试信息 ————————————————————————
    Outputs[0]['Context'] = result + '\n' + '\n'.join(debugging)
    return Outputs
