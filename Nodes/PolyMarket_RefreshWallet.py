import os
import sqlite3
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Any, Set

# **节点输入输出定义**
OutPutNum = 1
InPutNum = 4
NodeKind = 'Normal'

# **Initialize Outputs and Inputs arrays and assign names directly**
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

# Inputs 配置
Inputs[0]['Kind'] = 'String_FilePath'
Inputs[0]['name'] = 'FilePath'
Inputs[0]['Isnecessary'] = True
Inputs[0]['IsLabel'] = False

# 额外数据库来源（可选）：当主库数据不全时，从这些库中查找同 token 的最新记录来补齐
for i in range(1, InPutNum):
    Inputs[i]['Kind'] = 'String_FilePath'
    Inputs[i]['name'] = f'FilePath{i + 1}'
    Inputs[i]['Isnecessary'] = False
    Inputs[i]['IsLabel'] = False

# Outputs 配置
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Result'

FunctionIntroduction = (
    '组件功能（简述代码整体功能）\n'
    '这是一个数据库刷新节点，用于补齐 polyMarket_Wallet 表中缺失的列信息，并在完成后复制生成 polyMarket_Sell 表。'
    '节点从数据库中检索所有包含 token 字段的表，根据 token 字段匹配并按照 query_time_beijing 筛选最新记录，'
    '将最新记录的其他列信息补充到 polyMarket_Wallet 表中（仅填充空值，已存在的值不覆盖），'
    '最后将更新后的 polyMarket_Wallet 表复制为 polyMarket_Sell 表（如果已存在则覆盖）。\n\n'
    '代码功能摘要（概括核心算法或主要处理步骤）\n'
    '程序连接 SQLite 数据库，读取 polyMarket_Wallet 表作为目标表，然后遍历数据库中所有表，'
    '筛选出包含 token 和 query_time_beijing 字段的表作为数据源。对于 polyMarket_Wallet 中的每一行，'
    '根据 token 字段在所有源表中查找匹配记录，按照 query_time_beijing 降序排序（空值视为最旧）选择最新记录，'
    '将源记录中存在的且目标表中对应列为空的字段值填充到目标行，最后将更新后的数据写回数据库，'
    '并将完整的 polyMarket_Wallet 表复制为 polyMarket_Sell 表。\n\n'
    '参数\n```yaml\n'
    'inputs:\n'
    '  - name: FilePath\n    type: file\n    required: true\n    description: SQLite 数据库文件路径\n'
    'outputs:\n'
    '  - name: Result\n    type: string\n    description: 执行结果摘要信息（包括处理的记录数、更新的字段数、表复制状态等）\n```\n'
    '\n运行逻辑（用 - 列表描写详细流程）\n'
    '- 从输入节点获取数据库文件路径 FilePath\n'
    '- 连接 SQLite 数据库，读取 polyMarket_Wallet 表作为目标表\n'
    '- 获取数据库中所有表名，筛选出包含 token 和 query_time_beijing 字段的表作为数据源表\n'
    '- 对于 polyMarket_Wallet 中的每一行，提取其 token 值\n'
    '- 在所有源表中按 token 匹配记录，对每条匹配记录按照 query_time_beijing 进行排序（空值视为最旧，最新的在前）\n'
    '- 选择排序后的第一条记录作为最新记录\n'
    '- 遍历最新记录的所有字段，对于目标表中对应列为空（None、空字符串、NULL）的字段，使用源记录的值填充\n'
    '- 收集所有更新后的行，一次性写回 polyMarket_Wallet 表\n'
    '- 将 polyMarket_Wallet 表完整复制为 polyMarket_Sell 表（如果已存在则先删除再创建）\n'
    '- 生成执行摘要，包括处理的记录数、更新的字段数、表复制状态等信息，输出到 Result'
)


def _quote_ident(name: str) -> str:
    """安全包裹标识符，避免保留字/特殊字符"""
    return '"' + str(name).replace('"', '""') + '"'


def _get_table_columns(conn: sqlite3.Connection, table_name: str) -> List[str]:
    """获取表的列名列表"""
    try:
        rows = conn.execute(f'PRAGMA table_info({_quote_ident(table_name)})').fetchall()
        return [r[1] for r in rows]  # 第2列是列名
    except Exception:
        return []


def _get_table_columns_set(conn: sqlite3.Connection, table_name: str) -> Set[str]:
    """获取表的列名集合（用于快速查找）"""
    return set(_get_table_columns(conn, table_name))


def _is_empty_value(val: Any) -> bool:
    """判断值是否为空（None、空字符串、NULL字符串）"""
    if val is None:
        return True
    s = str(val).strip()
    return s == '' or s.upper() == 'NULL' or s.upper() == 'NONE'


def _parse_datetime_for_sort(dt_str: Optional[str]) -> datetime:
    """将日期时间字符串解析为 datetime 对象用于排序，空值返回最小日期"""
    if _is_empty_value(dt_str):
        return datetime.min
    try:
        # 尝试常见格式
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y/%m/%d %H:%M:%S',
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y/%m/%d %H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%S.%fZ',
        ]
        for fmt in formats:
            try:
                return datetime.strptime(str(dt_str).strip(), fmt)
            except ValueError:
                continue
        # 如果都不匹配，返回最小日期（视为最旧）
        return datetime.min
    except Exception:
        return datetime.min


def _copy_table(conn: sqlite3.Connection, source_table: str, target_table: str, debug_lines: List[str]) -> bool:
    """复制表：将 source_table 复制为 target_table，如果已存在则覆盖"""
    try:
        cur = conn.cursor()
        
        # 检查目标表是否存在
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (target_table,)
        )
        target_exists = cur.fetchone() is not None
        
        if target_exists:
            debug_lines.append(f"[copy] 目标表 {target_table} 已存在，将删除旧表")
            cur.execute(f'DROP TABLE {_quote_ident(target_table)}')
        
        # 创建新表并复制数据
        cur.execute(f'CREATE TABLE {_quote_ident(target_table)} AS SELECT * FROM {_quote_ident(source_table)}')
        conn.commit()
        
        # 验证复制结果
        cur.execute(f'SELECT COUNT(*) FROM {_quote_ident(target_table)}')
        row_count = cur.fetchone()[0]
        debug_lines.append(f"[copy] 成功复制表：{source_table} -> {target_table}，共 {row_count} 行")
        return True
    
    except Exception as e:
        debug_lines.append(f"[copy] 复制表失败: {e}")
        conn.rollback()
        return False


def run_node(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    """执行节点的主函数"""
    debug_lines = []
    summary = []
    conn = None
    extra_conns: List[sqlite3.Connection] = []
    
    try:
        # 获取输入文件路径
        file_path = node['Inputs'][0].get('Context') or ""
        if not file_path:
            raise ValueError("FilePath 输入为空")
        
        file_path = file_path.strip()
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"数据库文件不存在: {file_path}")
        
        debug_lines.append(f"[start] 数据库路径: {file_path}")

        # 收集额外数据库路径（可选）
        db_paths: List[str] = [file_path]
        try:
            for i in range(1, InPutNum):
                p = (node['Inputs'][i].get('Context') or "").strip()
                if not p:
                    continue
                if not os.path.exists(p):
                    debug_lines.append(f"[extra] 跳过不存在的数据库: {p}")
                    continue
                # 避免重复
                if os.path.abspath(p) == os.path.abspath(file_path):
                    continue
                db_paths.append(p)
        except Exception:
            # 输入结构异常时，不影响主流程
            pass
        
        # 连接数据库
        conn = sqlite3.connect(file_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")

        # 连接额外数据库（只读来源，不写入）
        for p in db_paths[1:]:
            try:
                c = sqlite3.connect(p, timeout=10.0)
                c.execute("PRAGMA busy_timeout=5000;")
                extra_conns.append(c)
                debug_lines.append(f"[extra] 加载额外来源库: {p}")
            except Exception as e:
                debug_lines.append(f"[extra] 打开额外来源库失败: {p} ({e})")
        
        # 获取所有表名
        def _list_tables(c: sqlite3.Connection) -> List[str]:
            try:
                return [
                    r[0] for r in c.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    ).fetchall()
                ]
            except Exception:
                return []

        all_tables = _list_tables(conn)
        debug_lines.append(f"[tables] 主库表数: {len(all_tables)}")
        
        # 检查 polyMarket_Wallet 表是否存在
        if 'polyMarket_Wallet' not in all_tables:
            raise ValueError("数据库中不存在 polyMarket_Wallet 表")
        
        # 读取目标表（保持原始数据类型，稍后再转换）
        wallet_df = pd.read_sql_query('SELECT * FROM "polyMarket_Wallet"', conn)
        debug_lines.append(f"[wallet] polyMarket_Wallet 表共有 {len(wallet_df)} 行")
        
        if wallet_df.empty:
            # 即使表为空，也要复制表
            copy_success = _copy_table(conn, 'polyMarket_Wallet', 'polyMarket_Sell', debug_lines)
            summary.append(f"polyMarket_Wallet 表为空，无需更新")
            summary.append(f"表复制: {'成功' if copy_success else '失败'}")
            Outputs[0]['Context'] = '\n'.join(summary + ['', '---- DEBUG DETAILS ----'] + debug_lines)
            if conn:
                conn.close()
            for c in extra_conns:
                try:
                    c.close()
                except Exception:
                    pass
            return Outputs
        
        wallet_cols = list(wallet_df.columns)
        wallet_cols_set = set(wallet_cols)
        debug_lines.append(f"[wallet] polyMarket_Wallet 表列数: {len(wallet_cols)}")
        
        # 筛选源表：必须包含 token 和 query_time_beijing 字段（主库 + 额外来源库）
        # source_refs: List[Tuple[conn, table_name, db_path]]
        source_refs = []

        def _collect_sources(c: sqlite3.Connection, tables: List[str], db_tag: str):
            for table_name in tables:
                if table_name in ('polyMarket_Wallet', 'polyMarket_Sell'):
                    continue
                cols_set = _get_table_columns_set(c, table_name)
                if 'token' in cols_set and 'query_time_beijing' in cols_set:
                    source_refs.append((c, table_name, db_tag))
                    if len(debug_lines) < 200:
                        debug_lines.append(f"[source] 发现源表: {table_name} ({db_tag})")

        _collect_sources(conn, all_tables, "main")
        for idx, c in enumerate(extra_conns):
            t = _list_tables(c)
            _collect_sources(c, t, f"extra{idx + 1}")

        if not source_refs:
            debug_lines.append("[source] 未找到包含 token 和 query_time_beijing 的源表（含额外库）")
        else:
            debug_lines.append(f"[source] 共找到 {len(source_refs)} 个源表（含额外库）")
        
        # 统计变量
        total_updated_rows = 0
        total_updated_fields = 0
        
        # 为每行钱包记录查找并补齐信息（仅在存在源表时执行）
        if source_refs:
            for wallet_idx, wallet_row in wallet_df.iterrows():
                token_val = wallet_row.get('token')
                if _is_empty_value(token_val):
                    continue  # 跳过 token 为空的行
                
                token_str = str(token_val).strip()
                best_match = None  # {table: str, row: dict, query_time: datetime, db: str}
                
                # 在所有源表中查找匹配的 token
                for source_conn, source_table, db_tag in source_refs:
                    try:
                        # 查询匹配的记录
                        query = f'SELECT * FROM {_quote_ident(source_table)} WHERE "token" = ?'
                        matches = pd.read_sql_query(query, source_conn, params=[token_str])
                        
                        if matches.empty:
                            continue
                        
                        # 按 query_time_beijing 排序（最新的在前）
                        matches['_sort_time'] = matches['query_time_beijing'].apply(_parse_datetime_for_sort)
                        matches = matches.sort_values('_sort_time', ascending=False)
                        matches = matches.drop(columns=['_sort_time'])
                        
                        # 取第一条（最新的）
                        latest_match = matches.iloc[0].to_dict()
                        match_time = _parse_datetime_for_sort(latest_match.get('query_time_beijing'))
                        
                        # 与当前最佳匹配比较
                        if best_match is None or match_time > best_match['query_time']:
                            best_match = {
                                'table': source_table,
                                'row': latest_match,
                                'query_time': match_time,
                                'db': db_tag
                            }
                    
                    except Exception as e:
                        debug_lines.append(f"[warning] 查询源表 {source_table} token={token_str} 时出错: {e}")
                        continue
                
                # 如果找到匹配记录，补齐空字段
                if best_match is not None:
                    source_row = best_match['row']
                    row_updated = False
                    field_count = 0
                    
                    for col_name in wallet_cols:
                        # 只填充目标表中为空的字段
                        wallet_val = wallet_row[col_name]
                        if _is_empty_value(wallet_val) and col_name in source_row:
                            source_val = source_row[col_name]
                            if not _is_empty_value(source_val):
                                wallet_df.at[wallet_idx, col_name] = source_val
                                row_updated = True
                                field_count += 1
                    
                    if row_updated:
                        total_updated_rows += 1
                        total_updated_fields += field_count
                        if len(debug_lines) < 100:  # 限制调试日志数量，避免输出过长
                            debug_lines.append(
                                f"[update] 行 {wallet_idx}: token={token_str}, "
                                f"源表={best_match['table']}({best_match.get('db','')}), 更新 {field_count} 个字段"
                            )
        
        # 写回数据库（如果有更新）
        if total_updated_rows > 0:
            # 将 DataFrame 转换为字符串格式（SQLite 需要 TEXT 类型）
            wallet_df = wallet_df.fillna('').astype(str)
            
            # 删除旧表数据并插入新数据
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(f'DELETE FROM {_quote_ident("polyMarket_Wallet")}')
                wallet_df.to_sql('polyMarket_Wallet', conn, if_exists='append', index=False)
                conn.commit()
                debug_lines.append(f"[save] 成功写回 {len(wallet_df)} 行数据到 polyMarket_Wallet")
            except Exception as e:
                conn.rollback()
                raise Exception(f"写回数据库失败: {e}")
        else:
            debug_lines.append(f"[save] 无需更新，保持原有数据")
        
        # 复制表：polyMarket_Wallet -> polyMarket_Sell
        copy_success = _copy_table(conn, 'polyMarket_Wallet', 'polyMarket_Sell', debug_lines)
        
        # 生成摘要
        summary.append(f"处理完成：共处理 {len(wallet_df)} 行")
        if source_tables:
            summary.append(f"更新了 {total_updated_rows} 行的数据")
            summary.append(f"总共填充了 {total_updated_fields} 个字段")
            summary.append(f"使用了 {len(source_tables)} 个源表")
        else:
            summary.append("未找到源表，跳过数据补齐")
        summary.append(f"表复制 polyMarket_Wallet -> polyMarket_Sell: {'成功' if copy_success else '失败'}")
        
        # 合并输出
        result_lines = summary + ['', '---- DEBUG DETAILS ----'] + debug_lines
        Outputs[0]['Context'] = '\n'.join(result_lines)
        
        if conn:
            conn.close()
        for c in extra_conns:
            try:
                c.close()
            except Exception:
                pass
        return Outputs
    
    except Exception as e:
        error_msg = f"执行失败: {type(e).__name__}: {e}"
        debug_lines.append(error_msg)
        Outputs[0]['Context'] = '\n'.join(['[ERROR] ' + error_msg, ''] + debug_lines)
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        for c in extra_conns:
            try:
                c.close()
            except Exception:
                pass
        return Outputs
