import re
import os
import sqlite3
from datetime import datetime, timezone, timedelta, date



# =========================
# Node metadata
# =========================
OutPutNum = 4
InPutNum = 3

#**Initialize Outputs and Inputs arrays and assign names directly
Outputs = [{'Num': None, 'Kind': None,'Boolean':False, 'Id': f'Output{i + 1}', 'Context': None,'name':f'OutPut{i + 1}','Link':0,'Description':'answer'} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Boolean':False,'Context': None, 'Isnecessary': True,'name':f'Input{i + 1}','Link':0,'IsLabel':False} for i in range(InPutNum)]

NodeKind = "Normal"
Lable = [{"Id": "Label1", "Kind": "None"}]

Inputs[0]["Kind"] = "String"
Inputs[0]["name"] = "NowTime"
Inputs[0]["Isnecessary"] = True

Inputs[1]["Kind"] = "String_FilePath"
Inputs[1]["name"] = "SavePath"
Inputs[1]["Isnecessary"] = False

Inputs[2]["Kind"] = "String"
Inputs[2]["name"] = "SaveName"
Inputs[2]["Isnecessary"] = False

Outputs[0]["Kind"] = "Boolean"
Outputs[0]["name"] = "IsTradingTime"
Outputs[0]["Description"] = "是否在美股常规交易时间（美东 周一~周五 09:30-16:00）"

Outputs[1]["Kind"] = "String"
Outputs[1]["name"] = "Save_Price"
Outputs[1]["Description"] = "本地数据库缓存到的最新价格（若可用），否则为空"

Outputs[2]["Kind"] = "String"
Outputs[2]["name"] = "Debug"
Outputs[2]["Description"] = "调试信息：是否读取到本地缓存、选用的db路径、失败原因等"

Outputs[3]["Kind"] = "String"
Outputs[3]["name"] = "data_json"
Outputs[3]["Description"] = "本地数据库 RealTime_Data 表最新一条的 data_json（若可用），否则为空"

FunctionIntroduction = (
    "组件功能：输入 nowtime（UTC ISO 时间字符串，例如 2026-02-02T03:26:05Z），判断当前是否处于美股常规交易时间，"
    "并在“非交易日（周末）且本地缓存存在”时，读取本地 SQLite 的 `__meta_cols` 获取最新价格，输出 Save_Price，"
    "用于下游跳过网络检索。\n\n"
    "说明：\n"
    "- 交易时段按“常规交易时段”计算：美东时间 周一~周五 09:30:00 <= t < 16:00:00\n"
    "- “非交易日”目前按周末判断（不含美股节假日与提前收盘；如需精确交易日历可再扩展）\n"
    "- 若提供 SavePath + SaveName 且 SQLite 内有 `__meta_cols` 表，会尝试读取："
    "table_name='RealTime_Data' AND col_name='data_price' 的 last_value\n\n"
    "- 判定策略（用于节省检索资源）：\n"
    "  - 交易时段：IsTradingTime=True\n"
    "  - 非交易时段且读到缓存：IsTradingTime=False（下游可跳过检索，直接用 Save_Price）\n"
    "  - 非交易时段但读不到缓存：IsTradingTime=True（下游继续检索）\n\n"
    "参数\n```yaml\n"
    "inputs:\n"
    "  - name: NowTime\n"
    "    type: string\n"
    "    required: true\n"
    "    description: UTC 时间（支持带 Z、带偏移、仅日期、或不带时区；不带时区默认按 UTC）\n"
    "  - name: SavePath\n"
    "    type: string (folder)\n"
    "    required: false\n"
    "    description: 本地 SQLite 保存目录\n"
    "  - name: SaveName\n"
    "    type: string\n"
    "    required: false\n"
    "    description: SQLite 文件名（可不带扩展名，默认补 .db）\n"
    "outputs:\n"
    "  - name: IsTradingTime\n"
    "    type: boolean\n"
    "    description: 是否在美股常规交易时间\n"
    "  - name: Save_Price\n"
    "    type: string\n"
    "    description: 可用时为本地缓存价格，否则为空\n"
    "  - name: Debug\n"
    "    type: string\n"
    "    description: 调试信息（定位为何未读到缓存）\n"
    "  - name: data_json\n"
    "    type: string\n"
    "    description: 本地数据库 RealTime_Data 最新 data_json（若可用）\n"
    "```\n"
)


# -------------------------
# time helpers
# -------------------------

def _safe_str(x) -> str:
    try:
        return "" if x is None else str(x)
    except Exception:
        return ""


def _clean_and_parse_time(raw) -> datetime:
    """
    支持：
    - 2025-12-31T12:00:00Z
    - 2025-12-31 12:00:00
    - 2025-12-31（仅日期）
    - 月/日可不补0：2025-12-1T14:00:00Z
    规则：若缺省时区，则按 UTC 处理。
    """
    s = _safe_str(raw).strip().strip('"').strip("'").strip()
    if not s:
        # 若无输入：用当前 UTC（避免节点直接崩）
        return datetime.now(timezone.utc)

    # 兼容：日期与时间用空格分隔
    if " " in s and "T" not in s:
        parts = s.split()
        if len(parts) >= 2:
            s = parts[0] + "T" + parts[1]

    # 补齐年月日（允许 1~2 位）
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})(.*)$", s)
    if m:
        y, mo, d, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        s = f"{y}-{int(mo):02d}-{int(d):02d}{rest}"

    # 仅日期：补齐到午夜 UTC
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        s = s + "T00:00:00+00:00"

    # 末尾 Z -> +00:00
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    # 若包含时间但没有时区（不含 +HH:MM / -HH:MM），默认按 UTC
    has_time = "T" in s
    has_tz = bool(re.search(r"([+-]\d{2}:\d{2})$", s))
    if has_time and (not has_tz):
        s = s + "+00:00"

    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """
    返回某年某月第 n 个 weekday 的日期。
    weekday: Monday=0 ... Sunday=6
    n: 1-based
    """
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    day = 1 + offset + (n - 1) * 7
    return date(year, month, day)


def _us_dst_window_utc(year: int):
    """
    计算美国东部时区（New York）DST 窗口的 UTC 边界：
    - 开始：3 月第二个周日 02:00（本地标准时 EST=UTC-5）=> 07:00 UTC
    - 结束：11 月第一个周日 02:00（本地夏令时 EDT=UTC-4）=> 06:00 UTC
    """
    dst_start_local = _nth_weekday_of_month(year, 3, 6, 2)  # Sunday=6, second Sunday
    dst_end_local = _nth_weekday_of_month(year, 11, 6, 1)   # first Sunday
    start_utc = datetime(year, 3, dst_start_local.day, 7, 0, 0, tzinfo=timezone.utc)
    end_utc = datetime(year, 11, dst_end_local.day, 6, 0, 0, tzinfo=timezone.utc)
    return start_utc, end_utc


def _us_eastern_offset_hours(dt_utc: datetime) -> int:
    """
    返回美东相对 UTC 的小时偏移：
    - 夏令时 EDT: -4
    - 标准时 EST: -5
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    else:
        dt_utc = dt_utc.astimezone(timezone.utc)
    start_utc, end_utc = _us_dst_window_utc(dt_utc.year)
    return -4 if (start_utc <= dt_utc < end_utc) else -5


def _is_us_regular_trading_time(dt_utc: datetime) -> bool:
    """
    美股常规交易时间（不含盘前/盘后）：
    美东 周一~周五 09:30:00 <= t < 16:00:00
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    dt_utc = dt_utc.astimezone(timezone.utc)
    offset_h = _us_eastern_offset_hours(dt_utc)
    dt_et = dt_utc + timedelta(hours=offset_h)  # 用 UTC 时区承载“当地时间”的时分秒
    wd = dt_et.weekday()  # Mon=0 ... Sun=6
    if wd >= 5:
        return False
    t = dt_et.time()
    return (t.hour > 9 or (t.hour == 9 and t.minute >= 30)) and (t.hour < 16)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _get_table_columns(conn: sqlite3.Connection, table_name: str) -> set:
    try:
        rows = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
        return {r[1] for r in rows}  # name
    except Exception:
        return set()


def _try_read_saved_cache(save_dir: str, save_name: str, dbg=None):
    """
    尝试读取本地 SQLite 缓存：
    - `__meta_cols`(table_name='RealTime_Data', col_name='data_price') 的 last_value 作为 Save_Price
    - `data_json` 优先从 `__meta_cols`(table_name='RealTime_Data', col_name='data_json') 的 last_value 读取（与 data_price 同逻辑）
      若未命中，再回退到 `RealTime_Data` 最新一条的 `data_json`（若存在该列），否则尝试 value_text 兜底
    返回：(save_price_float, save_price_str, data_json, db_used)
    """
    if dbg is None:
        dbg = []

    save_dir = _safe_str(save_dir).strip()
    save_name = _safe_str(save_name).strip().replace("\n", "").replace("\r", "")
    if not save_dir or not save_name:
        dbg.append("[cache] 未提供 SavePath/SaveName，跳过本地缓存读取")
        return None, "", "", ""

    if not (save_name.lower().endswith(".db") or save_name.lower().endswith(".sqlite")):
        save_name += ".db"

    full_path = os.path.join(save_dir, save_name)
    if not os.path.exists(full_path):
        dbg.append(f"[cache] DB 不存在：{full_path}")
        return None, "", "", full_path

    conn = None
    try:
        conn = sqlite3.connect(full_path, timeout=3.0)
        db_used = full_path

        # 1) 从 __meta_cols 读取 data_price 的 last_value
        save_price_s = ""
        save_price_f = None
        data_json = ""
        if _table_exists(conn, "__meta_cols"):
            try:
                row = conn.execute(
                    # __meta_cols 现在可能带 symbol 维度；不传 symbol 时应按更新时间取最新一条
                    'SELECT last_value FROM "__meta_cols" WHERE table_name=? AND col_name=? ORDER BY updated_at_utc DESC LIMIT 1',
                    ("RealTime_Data", "data_price"),
                ).fetchone()
            except Exception:
                # 兜底：极老 schema 可能没有 updated_at_utc
                row = conn.execute(
                    'SELECT last_value FROM "__meta_cols" WHERE table_name=? AND col_name=? LIMIT 1',
                    ("RealTime_Data", "data_price"),
                ).fetchone()
            if row and row[0] is not None:
                save_price_s = _safe_str(row[0]).strip()
                try:
                    save_price_f = float(save_price_s)
                except Exception:
                    save_price_f = None
                dbg.append(f"[cache] __meta_cols 命中 data_price：{save_price_s}")
            else:
                dbg.append("[cache] __meta_cols 未命中 (RealTime_Data, data_price)")

            # 1.1) 从 __meta_cols 读取 data_json 的 last_value（优先）
            try:
                rowj = conn.execute(
                    'SELECT last_value FROM "__meta_cols" WHERE table_name=? AND col_name=? ORDER BY updated_at_utc DESC LIMIT 1',
                    ("RealTime_Data", "data_json"),
                ).fetchone()
            except Exception:
                rowj = conn.execute(
                    'SELECT last_value FROM "__meta_cols" WHERE table_name=? AND col_name=? LIMIT 1',
                    ("RealTime_Data", "data_json"),
                ).fetchone()
            if rowj and rowj[0] is not None:
                data_json = _safe_str(rowj[0])
                dbg.append(f"[cache] __meta_cols 命中 data_json（len={len(data_json)}）")
            else:
                dbg.append("[cache] __meta_cols 未命中 (RealTime_Data, data_json)")
        else:
            dbg.append("[cache] DB 中不存在 __meta_cols（可能不是 JsonToSqlSave 生成的库）")

        # 2) 若 __meta_cols 未命中 data_json，则回退读取 RealTime_Data 最新一条 data_json / value_text
        if data_json is not None and _safe_str(data_json).strip():
            return save_price_f, save_price_s, data_json, db_used

        if _table_exists(conn, "RealTime_Data"):
            cols = _get_table_columns(conn, "RealTime_Data")
            pick_col = None
            if "data_json" in cols:
                pick_col = "data_json"
            elif "value_text" in cols:
                pick_col = "value_text"

            if pick_col:
                # 取最新一条“非空”内容，避免最新行刚好为空导致误判
                if pick_col == "data_json":
                    row2 = conn.execute(
                        'SELECT "data_json" FROM "RealTime_Data" WHERE "data_json" IS NOT NULL AND TRIM("data_json")<>"" ORDER BY id DESC LIMIT 1'
                    ).fetchone()
                else:
                    row2 = conn.execute(
                        f'SELECT "{pick_col}" FROM "RealTime_Data" WHERE "{pick_col}" IS NOT NULL AND TRIM("{pick_col}")<>"" ORDER BY id DESC LIMIT 1'
                    ).fetchone()
                if row2 and row2[0] is not None:
                    data_json = _safe_str(row2[0])
                    dbg.append(f"[cache] RealTime_Data 最新 {pick_col} 已读取（len={len(data_json)}）")
                else:
                    dbg.append(f"[cache] RealTime_Data 存在但最新 {pick_col} 为空")
            else:
                dbg.append('[cache] RealTime_Data 存在但未找到 "data_json"/"value_text" 列')
        else:
            dbg.append("[cache] DB 中不存在 RealTime_Data 表")

        return save_price_f, save_price_s, data_json, db_used
    except Exception as e:
        dbg.append(f"[cache][error] {type(e).__name__}: {_safe_str(e)}")
        return None, "", "", full_path
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass

# -------------------------
# main
# -------------------------
def run_node(node):
    dbg = []
    try:
        raw = None
        save_dir = ""
        save_name = ""
        try:
            inps = node.get("Inputs") or []
            inp0 = (inps[0] if len(inps) > 0 else None) or {}
            raw = inp0.get("Context")
            if raw is None:
                raw = inp0.get("Num")

            inp1 = (inps[1] if len(inps) > 1 else None) or {}
            save_dir = inp1.get("Context") or inp1.get("Num") or ""

            inp2 = (inps[2] if len(inps) > 2 else None) or {}
            save_name = inp2.get("Context") or inp2.get("Num") or ""
        except Exception:
            raw = None

        dt = _clean_and_parse_time(raw)
        dt_utc = dt.astimezone(timezone.utc)
        is_trading_time_raw = bool(_is_us_regular_trading_time(dt_utc))

        # 不在交易时段：尝试读取 Save_Price（用于下游跳过检索）
        save_price_f = None
        save_price_s = ""
        data_json = ""
        db_used = ""
        if not is_trading_time_raw:
            save_price_f, save_price_s, data_json, db_used = _try_read_saved_cache(str(save_dir), str(save_name), dbg=dbg)
        else:
            dbg.append("[cache] IsTradingTime=True（交易时段），按策略不读本地缓存")

        # 最终判定逻辑（按你的新需求）：
        # - 交易时段：True
        # - 非交易时段 + 读到缓存：False（节省检索）
        # - 非交易时段 + 读不到缓存：True（继续检索）
        # 这里的“缓存”不只包含价格，也包含 data_json（你现在的需求是希望能复用 data_json）
        has_cache_price = bool(save_price_s) or (save_price_f is not None)
        has_cache_data_json = bool(_safe_str(data_json).strip())
        has_cache = bool(has_cache_price or has_cache_data_json)

        is_trading_time_final = bool(is_trading_time_raw or (not has_cache))
        if (not is_trading_time_raw) and (not has_cache):
            dbg.append("[policy] 非交易时段但未读到缓存（既无 Save_Price 也无 data_json）：按策略强制 IsTradingTime=True 以继续检索")
        elif (not is_trading_time_raw) and has_cache:
            if has_cache_price and has_cache_data_json:
                dbg.append("[policy] 非交易时段且已读到缓存（Save_Price + data_json）：IsTradingTime=False 以节省检索")
            elif has_cache_price:
                dbg.append("[policy] 非交易时段且已读到缓存（Save_Price）：IsTradingTime=False 以节省检索")
            else:
                dbg.append("[policy] 非交易时段且已读到缓存（data_json）：IsTradingTime=False 以节省检索")

        Outputs[0]["Boolean"] = is_trading_time_final
        Outputs[0]["Context"] = "True" if is_trading_time_final else "False"

        Outputs[1]["Context"] = save_price_s or ""
        Outputs[1]["Num"] = save_price_f
        Outputs[2]["Context"] = "\n".join(dbg) if dbg else ""
        Outputs[3]["Context"] = data_json or ""
        return Outputs
    except Exception as e:
        # 关键：不要吞错，否则表现就是“输出全空”
        dbg.append(f"[node][error] {type(e).__name__}: {_safe_str(e)}")
        Outputs[0]["Boolean"] = False
        Outputs[0]["Context"] = "False"
        Outputs[1]["Context"] = ""
        Outputs[1]["Num"] = None
        Outputs[2]["Context"] = "\n".join(dbg) if dbg else ""
        Outputs[3]["Context"] = ""
        return Outputs


