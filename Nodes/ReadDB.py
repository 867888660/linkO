import os
import sqlite3
import copy

# ===== 节点定义 =====
OutPutNum = 2
InPutNum = 1

Outputs = [
    {
        'Num': None, 'Kind': None, 'Boolean': False,
        'Id': f'Output{i + 1}', 'Context': None,
        'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''
    }
    for i in range(OutPutNum)
]

Inputs = [
    {
        'Num': None, 'Kind': None,
        'Id': f'Input{i + 1}', 'Context': None,
        'Isnecessary': True, 'name': f'Input{i + 1}',
        'Link': 0, 'IsLabel': True
    }
    for i in range(InPutNum)
]

NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction = (
    '组件功能：读取 SQLite 数据库中的 Stock 和 Crypto 两张表，'
    '按 NowTime 列取最新时间点的数据，并自动回溯填补因去重机制产生的 NULL 值，'
    '将所有列以 key = value 的格式输出。\n\n'
    '去重回溯说明：\n'
    '  DataCollet2Sql 的去重规则会把未变化的列存为 NULL，\n'
    '  本组件会向前逐行回溯，找到每个列最近一次非 NULL 的值，\n'
    '  确保输出是完整的快照数据。\n\n'
    '参数\n```yaml\n'
    'inputs:\n'
    '  - name: db_path\n'
    '    type: String_FilePath\n'
    '    required: true\n'
    '    description: SQLite 数据库文件路径\n'
    'outputs:\n'
    '  - name: Stock\n'
    '    type: string\n'
    '    description: Stock 表最新完整快照（Price_XXX = val / McapUsd_XXX = val …）\n'
    '  - name: Crypto_Data\n'
    '    type: string\n'
    '    description: Crypto 表最新完整快照（Price_XXX = val / McapUsd_XXX = val …）\n'
    '```\n'
)

# 设置入参属性
Inputs[0]['Kind'] = 'String_FilePath'
Inputs[0]['name'] = 'db_path'
Inputs[0]['Isnecessary'] = True

# 设置出参属性
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Stock'
Outputs[1]['Kind'] = 'String'
Outputs[1]['name'] = 'Crypto_Data'

# 元数据列，不输出到结果
_SKIP_COLS = {'id', 'saved_at_utc'}


def _read_latest_snapshot_as_kv(conn, table_name):
    """
    读取指定表的最新完整快照：
    1. 按 NowTime DESC 取最新行
    2. 对于因去重机制而为 NULL 的列，向前回溯查找最近的非 NULL 值
    3. 以 "列名 = 值" 的多行文本返回
    """
    cur = conn.cursor()

    # 检查表是否存在
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    )
    if not cur.fetchone():
        return None, f"表 '{table_name}' 不存在"

    # 获取列名
    col_info = cur.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    col_names = [row[1] for row in col_info]

    if not col_names:
        return None, f"表 '{table_name}' 没有任何列"

    # 确定排序列：优先 NowTime，其次 saved_at_utc，最后 id
    has_nowtime = 'NowTime' in col_names
    if has_nowtime:
        order_col = 'NowTime'
    elif 'saved_at_utc' in col_names:
        order_col = 'saved_at_utc'
    elif 'id' in col_names:
        order_col = 'id'
    else:
        order_col = None

    # 业务列（排除元数据列）
    biz_cols = [c for c in col_names if c.lower() not in _SKIP_COLS]
    if not biz_cols:
        return None, f"表 '{table_name}' 没有业务列"

    # ========== 策略：逐列取最近非 NULL 值 ==========
    # 这样可以一次性解决去重 NULL 回溯问题，无论跨多少行
    snapshot = {}
    for col in biz_cols:
        if order_col:
            query = (
                f'SELECT "{col}" FROM "{table_name}" '
                f'WHERE "{col}" IS NOT NULL AND TRIM(CAST("{col}" AS TEXT)) != \'\' '
                f'ORDER BY "{order_col}" DESC LIMIT 1'
            )
        else:
            query = (
                f'SELECT "{col}" FROM "{table_name}" '
                f'WHERE "{col}" IS NOT NULL AND TRIM(CAST("{col}" AS TEXT)) != \'\' '
                f'ORDER BY rowid DESC LIMIT 1'
            )
        row = cur.execute(query).fetchone()
        if row and row[0] is not None:
            snapshot[col] = row[0]

    if not snapshot:
        return None, f"表 '{table_name}' 没有有效数据"

    # 输出（NowTime 也输出，方便下游知道数据时间点）
    lines = []
    for col in biz_cols:
        if col in snapshot:
            lines.append(f"{col} = {snapshot[col]}")

    return '\n'.join(lines), None


def run_node(node):
    db_path = (node.get('Inputs', [{}])[0].get('Context') or '').strip()

    if not db_path:
        Outputs[0]['Context'] = '错误：db_path 不能为空'
        Outputs[1]['Context'] = '错误：db_path 不能为空'
        return copy.deepcopy(Outputs)

    if not os.path.exists(db_path):
        Outputs[0]['Context'] = f'错误：数据库文件不存在 -> {db_path}'
        Outputs[1]['Context'] = f'错误：数据库文件不存在 -> {db_path}'
        return copy.deepcopy(Outputs)

    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=8)
        conn.execute("PRAGMA busy_timeout=8000;")

        # 读取 Stock 表
        stock_text, stock_err = _read_latest_snapshot_as_kv(conn, 'Stock')
        if stock_err:
            Outputs[0]['Context'] = f'Stock 读取失败：{stock_err}'
        else:
            Outputs[0]['Context'] = stock_text

        # 读取 Crypto 表
        crypto_text, crypto_err = _read_latest_snapshot_as_kv(conn, 'Crypto')
        if crypto_err:
            Outputs[1]['Context'] = f'Crypto 读取失败：{crypto_err}'
        else:
            Outputs[1]['Context'] = crypto_text

        return copy.deepcopy(Outputs)

    except Exception as e:
        Outputs[0]['Context'] = f'数据库读取失败：{e}'
        Outputs[1]['Context'] = f'数据库读取失败：{e}'
        return copy.deepcopy(Outputs)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
