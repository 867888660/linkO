import json
import re
from datetime import datetime, timezone


# **Define the number of outputs and inputs
OutPutNum = 1
InPutNum = 2
FunctionIntroduction='组件功能：这是一个计算两个时间差的功能组件，用于计算两个时间之间的差值（以天为单位）。\\n\\n代码功能摘要：接收两个时间字符串，做基础清洗与补齐（可容忍月/日不补0、可仅填日期、可带Z或不带时区），解析为datetime对象后计算时间差，输出天数差（可为负数），保留小数点后5位。\\n\\n参数：\\n```yaml\\ninputs:\\n  - name: Input1\\n    type: string\\n    required: true\\n    description: 第一个时间字符串，例如"2025-12-31T12:00:00Z" 或 "2025-12-31"\\n  - name: Input2\\n    type: string\\n    required: true\\n    description: 第二个时间字符串，例如"2025-12-31T14:00:00Z" 或 "2025-12-31 14:00:00"\\noutputs:\\n  - name: OutPut1\\n    type: string\\n    description: 时间差（天），保留小数点后5位（可为负）\\n```\\n\\n运行逻辑：\\n- 读取两个输入字符串\\n- 去除首尾空白与引号，规范化为可解析的ISO格式\\n- 解析为datetime（缺省时区按UTC处理）\\n- 计算时间差（Input1 - Input2）\\n- 换算为天并格式化到小数点后5位输出'
# **Define the number of outputs and inputs

# **Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Kind': None, 'Id': f'Output1{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': False} for i in range(InPutNum)]
# **Initialize Outputs and Inputs arrays and assign names directly
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# **Assign properties to Inputs
for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'
# **Assign properties to Inputs

# --- helpers ---
def _clean_and_parse_time(raw) -> datetime:
    """
    支持：
    - 2025-12-31T12:00:00Z
    - 2025-12-31 12:00:00
    - 2025-12-31（仅日期）
    - 月/日可不补0：2025-12-1T14:00:00Z
    规则：若缺省时区，则按 UTC 处理。
    """
    s = '' if raw is None else str(raw)
    s = s.strip().strip('"').strip("'").strip()

    # 兼容：日期与时间用空格分隔
    if ' ' in s and 'T' not in s:
        parts = s.split()
        if len(parts) >= 2:
            s = parts[0] + 'T' + parts[1]

    # 补齐年月日（允许 1~2 位）
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})(.*)$', s)
    if m:
        y, mo, d, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        s = f'{y}-{int(mo):02d}-{int(d):02d}{rest}'

    # 仅日期：补齐到午夜 UTC
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', s):
        s = s + 'T00:00:00+00:00'

    # 末尾 Z -> +00:00
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'

    # 若包含时间但没有时区（不含 +HH:MM / -HH:MM），默认按 UTC
    has_time = 'T' in s
    has_tz = bool(re.search(r'([+-]\d{2}:\d{2})$', s))
    if has_time and (not has_tz):
        # 纯 datetime：补时区
        s = s + '+00:00'

    dt = datetime.fromisoformat(s)
    # 若仍无 tzinfo（极端情况），强制 UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# **Function definition
def run_node(node):
    try:
        time1 = _clean_and_parse_time((node.get('Inputs') or [{}])[0].get('Context'))
        time2 = _clean_and_parse_time((node.get('Inputs') or [{}, {}])[1].get('Context'))

        # 重要：这里不再取 abs，允许输出负数；方向为 (Input1 - Input2)
        diff_seconds = (time1 - time2).total_seconds()
        diff_days = diff_seconds / 86400.0

        # 避免 -0.00000 这种显示（浮点舍入边界）
        txt = f"{diff_days:.5f}"
        if txt == "-0.00000":
            txt = "0.00000"

        # 端口类型仍为 String，但同时写入 Num 便于下游数值节点读取
        Outputs[0]['Num'] = diff_days
        Outputs[0]['Context'] = txt
        return Outputs
    except Exception:
        Outputs[0]['Num'] = None
        Outputs[0]['Context'] = ""
        return Outputs

