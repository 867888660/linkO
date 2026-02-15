import os
import sqlite3
from typing import Dict, List, Any, Tuple

# -----------------------------
# Node meta
# -----------------------------
OutPutNum = 1
InPutNum = 2
NodeKind = 'Normal'

Outputs = [
    {'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}',
     'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''}
    for i in range(OutPutNum)
]
Inputs = [
    {'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None,
     'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True}
    for i in range(InPutNum)
]

Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# Inputs: 两个数据库文件路径
Inputs[0]['Kind'] = 'String_FilePath'
Inputs[0]['name'] = 'SourceDB'
Inputs[0]['Isnecessary'] = True
Inputs[0]['IsLabel'] = False

Inputs[1]['Kind'] = 'String_FilePath'
Inputs[1]['name'] = 'TargetDB'
Inputs[1]['Isnecessary'] = True
Inputs[1]['IsLabel'] = False

# Output: 执行结果
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'result'

FunctionIntroduction = (
    '组件功能（简述代码整体功能）\n'
    '这是一个数据库搬迁节点：把源 SQLite 数据库中的 polyMarket_Wallet 表搬迁到目标 SQLite 数据库中。\n\n'
    '代码功能摘要（概括核心算法或主要处理步骤）\n'
    '节点接收源库路径与目标库路径，连接两个 SQLite 数据库；检查源库是否存在 polyMarket_Wallet 表；'
    '在目标库中删除同名旧表（若存在），再按源表建表 SQL 重建结构，并分批复制数据；最后输出搬迁结果。\n\n'
    '参数\n```yaml\ninputs:\n  - name: SourceDB\n    type: file\n    required: true\n    description: 源 SQLite 数据库文件路径\n  - name: TargetDB\n    type: file\n    required: true\n    description: 目标 SQLite 数据库文件路径\noutputs:\n  - name: result\n    type: string\n    description: 搬迁结果摘要（成功/失败、复制行数等）\n```\n\n'
    '运行逻辑（用 - 列表描写详细流程）\n'
    '- 读取 SourceDB / TargetDB 路径并校验\n'
    '- 连接源库与目标库\n'
    '- 校验源库存在 polyMarket_Wallet 表\n'
    '- 目标库若存在同名表则删除\n'
    '- 在目标库重建表结构\n'
    '- 分批复制数据到目标库\n'
    '- 输出执行结果'
)


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _get_create_table_sql(conn: sqlite3.Connection, table_name: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return (row[0] if row and row[0] else '') or ''


def _get_table_columns(conn: sqlite3.Connection, table_name: str) -> List[str]:
    try:
        rows = conn.execute(f'PRAGMA table_info({_quote_ident(table_name)})').fetchall()
        return [r[1] for r in rows]
    except Exception:
        return []


def _iter_table_rows(conn: sqlite3.Connection, table_name: str, batch_size: int = 1000):
    cur = conn.execute(f'SELECT * FROM {_quote_ident(table_name)}')
    while True:
        rows = cur.fetchmany(batch_size)
        if not rows:
            break
        yield rows


def _ensure_parent_dir(file_path: str) -> None:
    parent = os.path.dirname(os.path.abspath(file_path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def _migrate_table(src_conn: sqlite3.Connection, dst_conn: sqlite3.Connection, table_name: str) -> Tuple[int, str]:
    """
    迁移指定表：重建结构 + 复制数据
    返回：(copied_rows, message)
    """
    if not _table_exists(src_conn, table_name):
        return 0, f"源库不存在表: {table_name}"

    create_sql = _get_create_table_sql(src_conn, table_name).strip()
    if not create_sql:
        return 0, f"无法读取源表建表 SQL: {table_name}"

    cols = _get_table_columns(src_conn, table_name)
    if not cols:
        return 0, f"无法读取源表列信息: {table_name}"

    # 目标库：覆盖重建
    dst_conn.execute("PRAGMA foreign_keys=OFF;")
    dst_conn.execute("PRAGMA busy_timeout=5000;")

    dst_conn.execute("BEGIN;")
    try:
        if _table_exists(dst_conn, table_name):
            dst_conn.execute(f'DROP TABLE {_quote_ident(table_name)}')
        dst_conn.execute(create_sql)

        placeholders = ",".join(["?"] * len(cols))
        col_list = ",".join([_quote_ident(c) for c in cols])
        insert_sql = f'INSERT INTO {_quote_ident(table_name)} ({col_list}) VALUES ({placeholders})'

        copied = 0
        for batch in _iter_table_rows(src_conn, table_name, batch_size=1000):
            dst_conn.executemany(insert_sql, batch)
            copied += len(batch)

        dst_conn.commit()
        return copied, f"成功搬迁表 {table_name}，复制 {copied} 行"
    except Exception as e:
        try:
            dst_conn.rollback()
        except Exception:
            pass
        return 0, f"搬迁失败: {e}"


def run_node(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    table_name = "polyMarket_Wallet"

    def _ctx(i: int) -> str:
        try:
            v = node.get('Inputs', [])[i].get('Context')
            return (v or '').strip()
        except Exception:
            return ''

    src_path = _ctx(0)
    dst_path = _ctx(1)

    if not src_path:
        Outputs[0]['Context'] = "失败：SourceDB 输入为空"
        return Outputs
    if not dst_path:
        Outputs[0]['Context'] = "失败：TargetDB 输入为空"
        return Outputs
    if not os.path.exists(src_path):
        Outputs[0]['Context'] = f"失败：源库文件不存在: {src_path}"
        return Outputs

    try:
        _ensure_parent_dir(dst_path)
    except Exception as e:
        Outputs[0]['Context'] = f"失败：无法创建目标库目录: {e}"
        return Outputs

    src_conn = None
    dst_conn = None
    try:
        src_conn = sqlite3.connect(src_path, timeout=10.0)
        dst_conn = sqlite3.connect(dst_path, timeout=10.0)

        copied_rows, msg = _migrate_table(src_conn, dst_conn, table_name)
        Outputs[0]['Context'] = msg
        return Outputs
    except Exception as e:
        Outputs[0]['Context'] = f"失败：{e}"
        return Outputs
    finally:
        try:
            if src_conn is not None:
                src_conn.close()
        except Exception:
            pass
        try:
            if dst_conn is not None:
                dst_conn.close()
        except Exception:
            pass


