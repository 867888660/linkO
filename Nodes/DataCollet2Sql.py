import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# =========================
# Node metadata
# =========================
OutPutNum = 2
InPutNum = 3

Outputs = [
    {
        'Num': None, 'Context': None, 'Boolean': False, 'Kind': None,
        'Id': f'Output{i + 1}', 'name': f'OutPut{i + 1}', 'Link': 0
    }
    for i in range(OutPutNum)
]

Inputs = [
    {
        'Num': None, 'Context': None, 'Boolean': False, 'Kind': None,
        'Id': f'Input{i + 1}', 'Isnecessary': True, 'name': f'Input{i + 1}',
        'Link': 0, 'IsLabel': False
    }
    for i in range(InPutNum)
]

NodeKind = 'Normal'
InputIsAdd = False
OutputIsAdd = False
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# Input 1: 数据库完整路径（目录 + 文件名，如 D:/data/mydb.db）
Inputs[0]['Kind'] = 'String_FilePath'
Inputs[0]['name'] = 'DBPath'

# Input 2: 原始数据（可含 {raw_data:表名} 标签，未找到标签则自动建 default_data 表）
Inputs[1]['Kind'] = 'String'
Inputs[1]['name'] = 'raw_data'

# Input 3: 批次时间（可选）
Inputs[2]['Kind'] = 'String'
Inputs[2]['name'] = 'NowTime'
Inputs[2]['Isnecessary'] = False

Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Result'

Outputs[1]['Kind'] = 'String'
Outputs[1]['name'] = 'Full_Path'

FunctionIntroduction = (
    '组件功能：金融数据收集 → SQLite 存储（DataCollet2Sql）。\n\n'
    '使用 {raw_data:表名} 标签将不同数据路由到不同的表，例如：\n'
    '  {raw_data:价格数据} {"price":100,"vol":500}\n'
    '  {raw_data:持仓数据} {"long":10,"short":5}\n'
    '会自动创建 "价格数据" 和 "持仓数据" 两张表，并写入对应 JSON 记录。\n\n'
    '若未包含 {raw_data:表名} 标签，则所有数据自动写入 "default_data" 表。\n\n'
    '去重规则（列级别）：\n'
    '  每列值与该表最新一条记录的同列值比较，\n'
    '  若相同 → 写入 NULL（节省存储空间）；\n'
    '  若整行所有列都未变化 → 跳过本行不插入。\n\n'
    '支持的 JSON 格式：单个对象 / 数组 / JSONL / 多段 JSON 拼接。\n\n'
    '参数：\n'
    '```yaml\n'
    'inputs:\n'
    '  - name: DBPath\n'
    '    type: string (file path)\n'
    '    required: true\n'
    '    description: SQLite 数据库完整路径（如 D:/data/mydb.db，目录不存在会自动创建，无扩展名自动补 .db）\n'
    '  - name: raw_data\n'
    '    type: string\n'
    '    required: true\n'
    '    description: 带 {raw_data:表名} 标签的数据（可包含多段）；无标签时自动写入 default_data 表\n'
    '  - name: NowTime\n'
    '    type: string\n'
    '    required: false\n'
    '    description: 批次时间（优先使用；为空则取当前 UTC 时间）\n'
    'outputs:\n'
    '  - name: Result\n'
    '    type: string\n'
    '    description: 每张表的写入/跳过/错误统计摘要\n'
    '  - name: Full_Path\n'
    '    type: string\n'
    '    description: SQLite 文件完整路径\n'
    '```\n'
)


# =========================
# 常量
# =========================
_SQLITE_RESERVED_COLS = {"id", "saved_at_utc"}
_DEFAULT_TABLE = "default_data"


# =========================
# 工具函数
# =========================

def _safe_str(x: Any) -> str:
    """安全转字符串，None 返回空串。"""
    try:
        return "" if x is None else str(x)
    except Exception:
        return ""


def _sanitize_col_name(name: Any) -> str:
    """
    把任意 key 转成 SQLite 安全列名：
    - 保留 [A-Za-z0-9_] 与常用中文字符
    - 其它字符替换为 _
    - 不以数字开头
    - 避免保留列名冲突
    """
    s = _safe_str(name).strip()
    if not s:
        s = "col"
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "col"
    if re.match(r"^\d", s):
        s = "c_" + s
    if s.lower() in _SQLITE_RESERVED_COLS:
        s = s + "_v"
    return s


def _sanitize_table_name(name: str) -> str:
    """清理表名：去首尾空白，移除引号（防止 SQL 注入），保留中文等字符。"""
    s = name.strip().replace('"', '').replace("'", "")
    if not s:
        s = _DEFAULT_TABLE
    return s


def _to_sqlite_value(v: Any) -> Any:
    """
    把值转成 SQLite 可存储的标量：
    - dict/list → JSON 字符串
    - bool → 0/1
    - number → 原样
    - 其它 → str
    """
    if v is None:
        return None
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, (dict, list)):
        try:
            return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except Exception:
            return _safe_str(v)
    return _safe_str(v)


def _maybe_json_load(v: Any) -> Any:
    """如果 v 是 JSON 字符串，尝试解析；失败则返回原值。"""
    if not isinstance(v, str):
        return v
    s = v.strip()
    if not s:
        return v
    if not ((s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]"))):
        return v
    try:
        return json.loads(s)
    except Exception:
        return v


def _iter_json_from_text(text: str):
    """从字符串中用 raw_decode 扫描提取所有 JSON 对象/数组。"""
    s = _safe_str(text)
    if not s:
        return
    dec = json.JSONDecoder()
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch.isspace():
            i += 1
            continue
        if ch not in "{[":
            i += 1
            continue
        try:
            obj, j = dec.raw_decode(s, i)
            yield obj
            i = j
        except Exception:
            i += 1
    # 注意：此函数既服务于通用 JSON 解析，也会被行情 JSON 解析复用


def _normalize_to_records_generic(raw: Any) -> Tuple[List[Any], int]:
    """
    通用 JSON → 记录列表 解析逻辑（原始实现，供兜底使用）：
    - dict → [dict]
    - list → 逐元素展开
    - text → 尝试 JSON / 多段 JSON / JSONL
    返回: (records, parse_error_count)
    """
    errors = 0
    records: List[Any] = []

    if raw is None:
        return [], 0
    if isinstance(raw, dict):
        return [raw], 0
    if isinstance(raw, list):
        return list(raw), 0

    text = _safe_str(raw).strip()
    if not text:
        return [], 0

    # 1) 整段标准 JSON
    if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
        try:
            obj = json.loads(text)
            if isinstance(obj, list):
                return list(obj), 0
            return [obj], 0
        except Exception:
            pass

    # 2) 多段 JSON 拼接（{...}{...}）
    for obj in _iter_json_from_text(text):
        if isinstance(obj, list):
            records.extend(list(obj))
        else:
            records.append(obj)
    if records:
        return records, 0

    # 3) JSONL（逐行 json.loads）
    for line in text.splitlines():
        ln = line.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
            if isinstance(obj, list):
                records.extend(list(obj))
            else:
                records.append(obj)
        except Exception:
            errors += 1

    return records, errors


# =========================
# 行情 JSON 专用解析（参考 Nodes/MarketJson.py）
# =========================

def _safe_float_mj(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, bool):
            return None
        return float(x)
    except Exception:
        return None


def _safe_int_mj(x: Any) -> Optional[int]:
    try:
        if x is None:
            return None
        if isinstance(x, bool):
            return None
        if isinstance(x, str):
            xs = x.strip()
            if not xs:
                return None
            if re.fullmatch(r"-?\d+(\.0+)?", xs):
                xs = xs.split(".", 1)[0]
            return int(xs)
        return int(x)
    except Exception:
        return None


def _mj_normalize_to_objects(raw: Any) -> List[Any]:
    """
    参考 MarketJson._normalize_to_objects：
    把原始文本/对象归一成“JSON 对象列表”，支持：
      - dict / list
      - 字符串（可含多段 JSON 拼接）
      - list/tuple/set 混合
    """
    if raw is None:
        return []

    if isinstance(raw, (list, tuple, set)):
        out: List[Any] = []
        for it in raw:
            out.extend(_mj_normalize_to_objects(it))
        return out

    if isinstance(raw, dict):
        return [raw]

    text = _safe_str(raw).strip()
    if not text:
        return []

    if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
        try:
            return [json.loads(text)]
        except Exception:
            pass

    return list(_iter_json_from_text(text))


def _mj_iter_candidate_records(obj: Any):
    """从复杂对象中枚举出“可能的行情记录”（含 symbol 的 dict 或 data/result/rows/items 中的 dict）。"""
    if isinstance(obj, dict):
        if "symbol" in obj and isinstance(obj.get("symbol"), (str, int, float)):
            yield obj
        data = obj.get("data")
        if isinstance(data, list):
            for it in data:
                if isinstance(it, dict):
                    yield it
        for k in ("result", "rows", "items"):
            v = obj.get(k)
            if isinstance(v, list):
                for it in v:
                    if isinstance(it, dict):
                        yield it
    elif isinstance(obj, list):
        for it in obj:
            if isinstance(it, dict):
                yield it


def _mj_looks_like_crypto_row(r: Dict[str, Any]) -> bool:
    keys = set(r.keys())
    want = {
        "price",
        "vol_24h_base",
        "vol_24h_quote",
        "open_time_ms",
        "close_time_ms",
        "market_cap_usd",
        "fdv_usd",
        "circulating_supply",
        "total_supply",
        "max_supply",
        "fundamentals_last_updated",
    }
    return len(keys.intersection(want)) >= 3


def _mj_select_record(objs: List[Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    无显式 TargetSymbol 时，参考 MarketJson._select_record：
    - 从所有候选记录里挑一条“最像行情”的记录。
    - 返回 (记录dict, 使用的 symbol)。
    """
    best: Optional[Dict[str, Any]] = None
    best_score = -1
    best_sym: Optional[str] = None

    for o in objs:
        for r in _mj_iter_candidate_records(o):
            if not isinstance(r, dict):
                continue
            score = 0
            for k in (
                "price", "vol_24h_base", "vol_24h_quote",
                "market_cap_usd", "fdv_usd",
                "open_time_ms", "close_time_ms",
                "circulating_supply", "total_supply", "max_supply",
                "fundamentals_last_updated",
            ):
                if r.get(k) is not None:
                    score += 1

            rs = _safe_str(r.get("symbol")).strip().upper()
            if re.fullmatch(r"[A-Z0-9]{5,20}", rs or ""):
                score += 1

            if _mj_looks_like_crypto_row(r):
                score += 3

            if score > best_score:
                best = r
                best_score = score
                best_sym = rs or None

    if best is not None:
        return best, best_sym
    return None, None


def _mj_get_first(r: Dict[str, Any], keys: List[str]) -> Any:
    for k in keys:
        if k in r and r.get(k) is not None:
            return r.get(k)
    return None


def _mj_build_market_row(symbol: str, r: Dict[str, Any]) -> Dict[str, Any]:
    """
    把单条行情记录 r 转成一行“宽表”字典：
      - 列名兼容 MarketJson：Price_xxx, Vol24hBase_xxx, ...
      - 字段缺失则不生成对应列。
    """
    sym = (_safe_str(symbol) or _safe_str(r.get("symbol")) or "UNKNOWN").strip().upper() or "UNKNOWN"

    price = _safe_float_mj(_mj_get_first(r, ["price", "lastPrice", "last_price"]))
    vbase = _safe_float_mj(_mj_get_first(r, ["vol_24h_base", "volume", "vol24h_base"]))
    vquote = _safe_float_mj(_mj_get_first(r, ["vol_24h_quote", "quoteVolume", "vol24h_quote"]))
    mcap = _mj_get_first(r, ["market_cap_usd", "marketCapUsd", "mcap_usd"])
    fdv = _mj_get_first(r, ["fdv_usd", "fdvUsd", "fully_diluted_valuation"])
    circ = _mj_get_first(r, ["circulating_supply", "circulatingSupply"])
    total = _mj_get_first(r, ["total_supply", "totalSupply"])
    maxs = _mj_get_first(r, ["max_supply", "maxSupply"])
    open_ms = _mj_get_first(r, ["open_time_ms", "openTime", "open_time"])
    close_ms = _mj_get_first(r, ["close_time_ms", "closeTime", "close_time"])
    fund_last = _mj_get_first(r, ["fundamentals_last_updated", "fundLastUpdated", "last_updated"])

    open_i = _safe_int_mj(open_ms)
    close_i = _safe_int_mj(close_ms)
    if open_i is not None:
        open_ms = open_i
    if close_i is not None:
        close_ms = close_i

    def _num_int_first(v: Any) -> Any:
        vi = _safe_int_mj(v)
        if vi is not None:
            return vi
        vf = _safe_float_mj(v)
        if vf is not None:
            return vf
        return None

    def _num_float_first(v: Any) -> Any:
        vf = _safe_float_mj(v)
        if vf is not None:
            return vf
        vi = _safe_int_mj(v)
        if vi is not None:
            return float(vi)
        return None

    mcap = _num_int_first(mcap)
    fdv = _num_int_first(fdv)
    circ = _num_float_first(circ)
    total = _num_float_first(total)
    maxs = _num_float_first(maxs)

    row: Dict[str, Any] = {}

    def _set_if_not_none(key: str, val: Any):
        if val is not None:
            row[key] = val

    _set_if_not_none(f"Price_{sym}", price)
    _set_if_not_none(f"Vol24hBase_{sym}", vbase)
    _set_if_not_none(f"Vol24hQuote_{sym}", vquote)
    _set_if_not_none(f"McapUsd_{sym}", mcap)
    _set_if_not_none(f"FdvUsd_{sym}", fdv)
    _set_if_not_none(f"CircSupply_{sym}", circ)
    _set_if_not_none(f"TotalSupply_{sym}", total)
    _set_if_not_none(f"MaxSupply_{sym}", maxs)
    _set_if_not_none(f"OpenTimeMs_{sym}", open_ms)
    _set_if_not_none(f"CloseTimeMs_{sym}", close_ms)
    _set_if_not_none(f"FundLastUpdated_{sym}", fund_last)

    return row


def _normalize_to_records(raw: Any) -> Tuple[List[Any], int]:
    """
    增强版记录归一化：
    1. 优先尝试按 MarketJson 的“行情解码方式”提取行情记录，并“横向合并”为一条宽表记录：
       - 对所有包含 symbol 的候选记录，分别构造 Price_xxx / McapUsd_xxx 等字段；
       - 多个 symbol 会合并成一行（不同 symbol 使用不同后缀，不会互相覆盖）。
    2. 若无法识别为行情 JSON，则回退到通用 JSON 解析逻辑。
    """
    try:
        objs = _mj_normalize_to_objects(raw)
        if objs:
            flat: Dict[str, Any] = {}
            found = False
            for o in objs:
                for r in _mj_iter_candidate_records(o):
                    if not isinstance(r, dict):
                        continue
                    sym = _safe_str(r.get("symbol")) or "UNKNOWN"
                    row = _mj_build_market_row(sym, r)
                    if row:
                        found = True
                        # 多个 symbol 的字段合并到一行，列名自带 symbol 后缀，不会互相覆盖
                        flat.update(row)
            if found and flat:
                return [flat], 0
    except Exception:
        # 行情解析失败时不抛错，交给通用逻辑兜底
        pass

    # 回退到原始通用解析
    return _normalize_to_records_generic(raw)




def _pivot_by_symbol(records: List[Any]) -> List[Any]:
    """
    检测是否为"带 symbol 的数组"（每条都是 dict 且都有 symbol 字段）。
    如果是 → 展开成一条宽行：字段名_SYMBOL = 值，例如 price_AAPL = 263.75。
    symbol 字段本身不写入。
    如果不是 → 原样返回。

    容错增强：
    - 允许 records 中混入少量非 dict / 无 symbol 记录，这些记录会被原样保留在结果中；
    - 只要至少有 2 条合法的带 symbol 记录，就会对其做“横向展开”。
    """
    if len(records) < 2:
        # 太少，不值得判断为“symbol 横向展开”场景
        return records

    # 只把“dict 且含 symbol 字段”的记录视为可展开对象，其他记录保留在外面
    valid_for_pivot: List[Dict[str, Any]] = []
    others: List[Any] = []
    for r in records:
        if isinstance(r, dict) and "symbol" in r:
            valid_for_pivot.append(r)
        else:
            others.append(r)

    # 至少需要 2 条合法记录才进行横向展开，否则直接原样返回
    if len(valid_for_pivot) < 2:
        return records

    flat: Dict[str, Any] = {}
    for r in valid_for_pivot:
        sym = _safe_str(r.get("symbol")).strip()
        if not sym:
            continue
        for k, v in r.items():
            kl = _safe_str(k).strip().lower()
            if kl == "symbol":
                continue
            col = f"{k}_{sym}"
            flat[col] = v

    # 若最终没生成任何列，说明 symbol 值都空等问题，保底返回原始 records
    if not flat:
        return records

    # 把展开后的宽行放在最前面，其余不参与展开的记录跟在后面
    if others:
        return [flat] + others
    return [flat]


def _parse_raw_data_sections(text: str) -> List[Tuple[str, str]]:
    """
    解析 {raw_data:表名} 标签，提取 (表名, JSON文本) 列表。

    示例输入：
      {raw_data:价格数据} {"price":100} {raw_data:持仓数据} {"long":10}
    返回：
      [("价格数据", '{"price":100}'), ("持仓数据", '{"long":10}')]

    若未找到任何标签 → 返回 [("default_data", 原始全文)]，自动使用默认表。
    """
    pattern = r'\{raw_data:([^}]+)\}'
    tags = list(re.finditer(pattern, text))

    # 未找到标签 → 所有数据路由到默认表
    if not tags:
        return [(_DEFAULT_TABLE, text)]

    sections: List[Tuple[str, str]] = []
    for i, match in enumerate(tags):
        table_name = _sanitize_table_name(match.group(1))
        start = match.end()
        end = tags[i + 1].start() if i + 1 < len(tags) else len(text)
        json_text = text[start:end].strip()
        if table_name and json_text:
            sections.append((table_name, json_text))
    return sections


# =========================
# 数据库辅助
# =========================

def _ensure_db(conn: sqlite3.Connection):
    """初始化数据库：设置 PRAGMA + 创建元数据表 __meta_cols。"""
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    cur.execute("PRAGMA busy_timeout=5000;")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS "__meta_cols" (
            table_name TEXT NOT NULL,
            col_name   TEXT NOT NULL,
            last_value TEXT,
            updated_at_utc TEXT,
            PRIMARY KEY (table_name, col_name)
        );
        """
    )
    conn.commit()


def _ensure_table(conn: sqlite3.Connection, table: str):
    """确保业务表存在（含 id 自增主键 + saved_at_utc 时间戳列）。"""
    cur = conn.cursor()
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS "{table}" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            saved_at_utc TEXT NOT NULL
        );
        """
    )
    safe_idx = _sanitize_col_name(table)
    cur.execute(f'CREATE INDEX IF NOT EXISTS "idx_{safe_idx}_saved_at" ON "{table}"(saved_at_utc);')
    conn.commit()


def _get_existing_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    rows = conn.cursor().execute(f'PRAGMA table_info("{table}")').fetchall()
    return [r[1] for r in rows]


def _ensure_columns(conn: sqlite3.Connection, table: str, col_names: List[str],
                     existing_cols_cache: Dict[str, set]):
    """确保列存在；不存在就 ALTER TABLE ADD COLUMN。"""
    if table not in existing_cols_cache:
        existing_cols_cache[table] = set(_get_existing_columns(conn, table))

    existing = existing_cols_cache[table]
    cur = conn.cursor()
    changed = False
    for c in col_names:
        if c in existing:
            continue
        cur.execute(f'ALTER TABLE "{table}" ADD COLUMN "{c}" TEXT;')
        existing.add(c)
        changed = True
    if changed:
        conn.commit()


def _get_last_col_value(conn: sqlite3.Connection, table: str, col: str) -> Optional[str]:
    """获取某表某列的 last_value（用于去重比较）。"""
    try:
        row = conn.cursor().execute(
            'SELECT last_value FROM "__meta_cols" WHERE table_name = ? AND col_name = ? LIMIT 1',
            (table, col),
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def _set_last_col_value(conn: sqlite3.Connection, table: str, col: str, value: Optional[str]):
    """写入某表某列的 last_value。"""
    try:
        conn.cursor().execute(
            """
            INSERT INTO "__meta_cols"(table_name, col_name, last_value, updated_at_utc)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(table_name, col_name) DO UPDATE SET
                last_value=excluded.last_value,
                updated_at_utc=excluded.updated_at_utc;
            """,
            (table, col, value, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    except Exception:
        pass


# =========================
# 主流程
# =========================

def run_node(node):
    db_path_raw = _safe_str(node['Inputs'][0].get('Context')).strip().replace("\n", "").replace("\r", "")
    raw_data = node['Inputs'][1].get('Context')
    now_time = node['Inputs'][2].get('Context') if len(node.get('Inputs', [])) > 2 else None

    # ---------- 参数校验 ----------
    if not db_path_raw:
        Outputs[0]['Context'] = "Error: DBPath 不能为空"
        Outputs[1]['Context'] = ""
        return Outputs

    raw_text = _safe_str(raw_data).strip()
    if not raw_text:
        Outputs[0]['Context'] = "Error: raw_data 不能为空"
        Outputs[1]['Context'] = ""
        return Outputs

    # 自动补扩展名
    if not (db_path_raw.lower().endswith(".db") or db_path_raw.lower().endswith(".sqlite")):
        db_path_raw += ".db"

    full_path = os.path.abspath(db_path_raw)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    # ---------- 解析 {raw_data:表名} 分段 ----------
    # 未找到标签时，_parse_raw_data_sections 自动回退到 default_data 表
    sections = _parse_raw_data_sections(raw_text)
    if not sections:
        Outputs[0]['Context'] = "Error: raw_data 解析后无有效数据段"
        Outputs[1]['Context'] = full_path
        return Outputs

    # 统一批次时间
    now_time_s = _safe_str(now_time).strip()
    saved_at_utc = now_time_s or datetime.now(timezone.utc).isoformat()

    try:
        conn = sqlite3.connect(full_path, timeout=5.0)
        try:
            _ensure_db(conn)
            existing_cols_cache: Dict[str, set] = {}
            # meta 缓存：(table, col) → last_value，减少频繁查库
            last_col_cache: Dict[Tuple[str, str], Optional[str]] = {}
            cur = conn.cursor()

            # 每张表的统计
            table_stats: Dict[str, Dict[str, int]] = {}

            def _norm_cmp(sql_val: Any) -> Optional[str]:
                """归一化为字符串用于去重比较"""
                if sql_val is None:
                    return None
                try:
                    return str(sql_val)
                except Exception:
                    return _safe_str(sql_val)

            def _get_last_cached(table: str, col: str) -> Optional[str]:
                key = (table, col)
                if key not in last_col_cache:
                    last_col_cache[key] = _get_last_col_value(conn, table, col)
                return last_col_cache[key]

            def _set_last_cached(table: str, col: str, val: Optional[str]):
                _set_last_col_value(conn, table, col, val)
                last_col_cache[(table, col)] = val

            # ---------- 逐段处理 ----------
            for table_name, json_text in sections:
                _ensure_table(conn, table_name)
                if table_name not in table_stats:
                    table_stats[table_name] = {"inserted": 0, "skipped": 0, "errors": 0}
                stats = table_stats[table_name]

                records, parse_err = _normalize_to_records(json_text)
                stats["errors"] += parse_err
                valid_records = [r for r in records if r is not None]

                # 带 symbol 的数组 → 展开成宽行（price_AAPL, price_MSFT, ...）
                valid_records = _pivot_by_symbol(valid_records)

                for r in valid_records:
                    try:
                        if isinstance(r, dict):
                            # ---- dict 记录：按列去重 ----
                            row_cols: List[str] = []
                            row_vals: List[Any] = []
                            changed_meta: List[Tuple[str, Optional[str]]] = []
                            has_change = False

                            for k, v in r.items():
                                col = _sanitize_col_name(k)
                                sql_val = _to_sqlite_value(v)
                                cur_v = _norm_cmp(sql_val)
                                last_v = _get_last_cached(table_name, col)

                                row_cols.append(col)
                                if cur_v == last_v:
                                    # 值未变化 → 写入 NULL 节省空间
                                    row_vals.append(None)
                                else:
                                    # 值变化 → 写入实际值，并记录需更新 meta
                                    has_change = True
                                    row_vals.append(sql_val)
                                    changed_meta.append((col, cur_v))

                            if not has_change:
                                # 整行无变化 → 跳过不插入
                                stats["skipped"] += 1
                                continue

                            _ensure_columns(conn, table_name, row_cols, existing_cols_cache)
                            cols = ["saved_at_utc"] + row_cols
                            vals = [saved_at_utc] + row_vals
                            placeholders = ",".join(["?"] * len(cols))
                            col_sql = ",".join([f'"{c}"' for c in cols])
                            cur.execute(
                                f'INSERT INTO "{table_name}"({col_sql}) VALUES({placeholders})',
                                vals,
                            )
                            stats["inserted"] += 1

                            # 更新 meta：仅更新变化的列
                            for c, vv in changed_meta:
                                _set_last_cached(table_name, c, vv)

                        else:
                            # ---- 非 dict（纯值）：存入 value_text 列 ----
                            sql_val = _to_sqlite_value(r)
                            cur_v = _norm_cmp(sql_val)
                            if cur_v == _get_last_cached(table_name, "value_text"):
                                stats["skipped"] += 1
                                continue

                            _ensure_columns(conn, table_name, ["value_text"], existing_cols_cache)
                            cur.execute(
                                f'INSERT INTO "{table_name}"("saved_at_utc","value_text") VALUES(?,?)',
                                (saved_at_utc, sql_val),
                            )
                            stats["inserted"] += 1
                            _set_last_cached(table_name, "value_text", cur_v)

                    except Exception:
                        stats["errors"] += 1

            conn.commit()
        finally:
            try:
                conn.close()
            except Exception:
                pass

        # ---------- 输出摘要 ----------
        lines = [f"Saved to SQLite: {full_path}", "Tables:"]
        for tbl, st in table_stats.items():
            lines.append(
                f"  - {tbl} (Inserted={st['inserted']}, Skipped={st['skipped']}, Errors={st['errors']})"
            )
        Outputs[0]['Context'] = "\n".join(lines)
        Outputs[1]['Context'] = full_path
        return Outputs

    except Exception as e:
        Outputs[0]['Context'] = f"Error: 写入 SQLite 失败: {e}\nDB: {full_path}"
        Outputs[1]['Context'] = full_path
        return Outputs
