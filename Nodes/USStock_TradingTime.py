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
    "- “非交易日”包含：周末 + 常见美股休市日（如 Presidents’ Day、MLK、Good Friday、感恩节等；不含提前收盘与罕见一次性停市）\n"
    "- 新增“是否最新”判定：若能从 `__meta_cols` 读取 `RealTime_Data/__table_updated_time`，且其与 NowTime 之间经历过任意常规交易时段，则视为缓存过期，强制 IsTradingTime=True 触发更新\n"
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


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """
    返回某年某月最后一个 weekday 的日期。
    weekday: Monday=0 ... Sunday=6
    """
    # 从下月 1 号往回推
    if month == 12:
        first_next = date(year + 1, 1, 1)
    else:
        first_next = date(year, month + 1, 1)
    cur = first_next - timedelta(days=1)
    while cur.weekday() != weekday:
        cur = cur - timedelta(days=1)
    return cur


def _easter_sunday_gregorian(year: int) -> date:
    """
    计算公历复活节（Easter Sunday）日期（Meeus/Jones/Butcher 算法）。
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _observed_date_for_fixed_holiday(local_d: date) -> date:
    """
    固定日期假期的“观察日”(Observed)：
    - 落在周六：提前到周五
    - 落在周日：顺延到周一
    - 否则：当天
    """
    wd = local_d.weekday()
    if wd == 5:  # Saturday
        return local_d - timedelta(days=1)
    if wd == 6:  # Sunday
        return local_d + timedelta(days=1)
    return local_d


def _us_market_holidays_et(year: int) -> set:
    """
    NYSE/Nasdaq 常见全日休市（按美东“本地日期”）。
    说明：这里覆盖常规每年固定/规则假期；未覆盖历史性一次性停市（如国家哀悼日）与极少见特殊情况。
    """
    hol = set()

    # New Year's Day (Jan 1) observed
    hol.add(_observed_date_for_fixed_holiday(date(year, 1, 1)))

    # Martin Luther King Jr. Day: third Monday in January
    hol.add(_nth_weekday_of_month(year, 1, 0, 3))

    # Presidents’ Day (Washington’s Birthday): third Monday in February
    hol.add(_nth_weekday_of_month(year, 2, 0, 3))

    # Good Friday: Friday before Easter Sunday
    easter = _easter_sunday_gregorian(year)
    hol.add(easter - timedelta(days=2))

    # Memorial Day: last Monday in May
    hol.add(_last_weekday_of_month(year, 5, 0))

    # Juneteenth: June 19 observed (NYSE started in 2022)
    if year >= 2022:
        hol.add(_observed_date_for_fixed_holiday(date(year, 6, 19)))

    # Independence Day: July 4 observed
    hol.add(_observed_date_for_fixed_holiday(date(year, 7, 4)))

    # Labor Day: first Monday in September
    hol.add(_nth_weekday_of_month(year, 9, 0, 1))

    # Thanksgiving Day: fourth Thursday in November
    hol.add(_nth_weekday_of_month(year, 11, 3, 4))  # Thursday=3

    # Christmas Day: Dec 25 observed
    hol.add(_observed_date_for_fixed_holiday(date(year, 12, 25)))

    # 过滤：只保留落在 year 内的 observed 日期（避免 1/1 周六导致 observed 变成上一年 12/31）
    return {d for d in hol if d.year == year}


def _is_us_market_holiday_et(local_d: date) -> bool:
    """
    判断某个“美东本地日期”是否为休市日（含 observed）。
    为处理跨年 observed（如 1/1 落周六 => 12/31 前一年 observed），这里会同时检查前后年份集合。
    """
    y = local_d.year
    hol = set()
    hol |= _us_market_holidays_et(y - 1)
    hol |= _us_market_holidays_et(y)
    hol |= _us_market_holidays_et(y + 1)
    return local_d in hol


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


def _us_dst_window_local_dates(year: int):
    """
    计算纽约时区 DST 窗口的“本地日期”边界：
    - 开始日：3 月第二个周日
    - 结束日：11 月第一个周日
    注意：交易时段发生在白天（09:30-16:00），对周一~周五来说，同一“本地日期”内偏移不会跨 DST 边界。
    """
    dst_start_local = _nth_weekday_of_month(year, 3, 6, 2)  # second Sunday of March
    dst_end_local = _nth_weekday_of_month(year, 11, 6, 1)   # first Sunday of Nov
    return dst_start_local, dst_end_local


def _us_eastern_offset_hours_for_local_date(local_d: date) -> int:
    """
    给定“美东本地日期”，返回该日期白天交易时段使用的偏移（EDT=-4, EST=-5）。
    这里按日期判断足够准确：DST 切换发生在周日凌晨 02:00，本函数主要服务于周一~周五交易窗计算。
    """
    start_d, end_d = _us_dst_window_local_dates(local_d.year)
    # DST 生效区间：start_d(周日)之后，到 end_d(周日)之前
    return -4 if (start_d < local_d < end_d) else -5


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
    # 休市日（按美东本地日期）
    if _is_us_market_holiday_et(dt_et.date()):
        return False
    t = dt_et.time()
    return (t.hour > 9 or (t.hour == 9 and t.minute >= 30)) and (t.hour < 16)


def _has_us_regular_trading_between(dt_updated_utc: datetime, dt_now_utc: datetime) -> bool:
    """
    判定在 (dt_updated_utc, dt_now_utc] 区间内，是否“经历过任意一段”美股常规交易时间窗口。
    若经历过，说明缓存数据不是“最新一轮交易后”的结果，应触发更新。
    """
    if dt_updated_utc is None or dt_now_utc is None:
        return False
    if dt_updated_utc.tzinfo is None:
        dt_updated_utc = dt_updated_utc.replace(tzinfo=timezone.utc)
    else:
        dt_updated_utc = dt_updated_utc.astimezone(timezone.utc)
    if dt_now_utc.tzinfo is None:
        dt_now_utc = dt_now_utc.replace(tzinfo=timezone.utc)
    else:
        dt_now_utc = dt_now_utc.astimezone(timezone.utc)

    if dt_now_utc <= dt_updated_utc:
        return False

    # 粗略映射到“本地日期”范围（加前后各 1 天防止边界误差）
    start_et = dt_updated_utc + timedelta(hours=_us_eastern_offset_hours(dt_updated_utc))
    end_et = dt_now_utc + timedelta(hours=_us_eastern_offset_hours(dt_now_utc))
    d0 = start_et.date() - timedelta(days=1)
    d1 = end_et.date() + timedelta(days=1)

    cur = d0
    while cur <= d1:
        # 周末无常规交易
        if cur.weekday() < 5:
            # 休市日无常规交易
            if _is_us_market_holiday_et(cur):
                cur = cur + timedelta(days=1)
                continue
            offset_h = _us_eastern_offset_hours_for_local_date(cur)
            # 交易窗：本地 09:30-16:00 => UTC = local - offset
            open_utc = datetime(cur.year, cur.month, cur.day, 9, 30, 0, tzinfo=timezone.utc) - timedelta(hours=offset_h)
            close_utc = datetime(cur.year, cur.month, cur.day, 16, 0, 0, tzinfo=timezone.utc) - timedelta(hours=offset_h)

            # 窗口与 (updated, now] 有交集即算“经历过交易时段”
            if max(open_utc, dt_updated_utc) < min(close_utc, dt_now_utc):
                return True

        cur = cur + timedelta(days=1)
    return False


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
    返回：(save_price_float, save_price_str, data_json, table_updated_time_utc, db_used)
    """
    if dbg is None:
        dbg = []

    save_dir = _safe_str(save_dir).strip()
    save_name = _safe_str(save_name).strip().replace("\n", "").replace("\r", "")
    if not save_dir or not save_name:
        dbg.append("[cache] 未提供 SavePath/SaveName，跳过本地缓存读取")
        return None, "", "", None, ""

    if not (save_name.lower().endswith(".db") or save_name.lower().endswith(".sqlite")):
        save_name += ".db"

    full_path = os.path.join(save_dir, save_name)
    if not os.path.exists(full_path):
        dbg.append(f"[cache] DB 不存在：{full_path}")
        return None, "", "", None, full_path

    conn = None
    try:
        conn = sqlite3.connect(full_path, timeout=3.0)
        db_used = full_path

        # 1) 从 __meta_cols 读取 data_price 的 last_value
        save_price_s = ""
        save_price_f = None
        data_json = ""
        table_updated_time_utc = None
        if _table_exists(conn, "__meta_cols"):
            # 0) 读取“表更新时间” __table_updated_time（用于判断缓存是否最新）
            try:
                rowt = conn.execute(
                    'SELECT last_value FROM "__meta_cols" WHERE table_name=? AND col_name=? ORDER BY updated_at_utc DESC LIMIT 1',
                    ("RealTime_Data", "__table_updated_time"),
                ).fetchone()
            except Exception:
                rowt = conn.execute(
                    'SELECT last_value FROM "__meta_cols" WHERE table_name=? AND col_name=? LIMIT 1',
                    ("RealTime_Data", "__table_updated_time"),
                ).fetchone()
            if rowt and rowt[0] is not None:
                try:
                    table_updated_time_utc = _clean_and_parse_time(rowt[0]).astimezone(timezone.utc)
                    dbg.append(f"[cache] __meta_cols 命中 __table_updated_time：{table_updated_time_utc.isoformat().replace('+00:00','Z')}")
                except Exception as _e:
                    table_updated_time_utc = None
                    dbg.append(f"[cache] __meta_cols 命中 __table_updated_time 但解析失败：{_safe_str(rowt[0])}")
            else:
                dbg.append("[cache] __meta_cols 未命中 (RealTime_Data, __table_updated_time)")

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
            return save_price_f, save_price_s, data_json, table_updated_time_utc, db_used

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

        return save_price_f, save_price_s, data_json, table_updated_time_utc, db_used
    except Exception as e:
        dbg.append(f"[cache][error] {type(e).__name__}: {_safe_str(e)}")
        return None, "", "", None, full_path
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
        dt_now_utc = dt.astimezone(timezone.utc)
        is_trading_time_raw = bool(_is_us_regular_trading_time(dt_now_utc))

        # 不在交易时段：尝试读取 Save_Price（用于下游跳过检索）
        save_price_f = None
        save_price_s = ""
        data_json = ""
        table_updated_time_utc = None
        db_used = ""
        if not is_trading_time_raw:
            save_price_f, save_price_s, data_json, table_updated_time_utc, db_used = _try_read_saved_cache(str(save_dir), str(save_name), dbg=dbg)
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

        # 新增：缓存“是否最新”判定——若 (table_updated_time, now] 中经历过任意常规交易时段，则强制更新
        stale_due_to_trading = False
        freshness_checked = False
        freshness_error = False
        if (not is_trading_time_raw) and has_cache and (table_updated_time_utc is not None):
            try:
                stale_due_to_trading = bool(_has_us_regular_trading_between(table_updated_time_utc, dt_now_utc))
                freshness_checked = True
            except Exception as _e:
                stale_due_to_trading = False
                freshness_error = True
                dbg.append(f"[freshness][error] {type(_e).__name__}: {_safe_str(_e)}")

        if stale_due_to_trading:
            dbg.append(
                "[freshness] __table_updated_time 与 NowTime 之间经历过常规交易时段：缓存不是最新，强制 IsTradingTime=True 触发更新"
            )
        elif freshness_checked and (not freshness_error):
            dbg.append("[freshness] __table_updated_time 与 NowTime 之间未经历常规交易时段：缓存可视为最新")

        is_trading_time_final = bool(is_trading_time_raw or (not has_cache) or stale_due_to_trading)
        if (not is_trading_time_raw) and (not has_cache):
            dbg.append("[policy] 非交易时段但未读到缓存（既无 Save_Price 也无 data_json）：按策略强制 IsTradingTime=True 以继续检索")
        elif (not is_trading_time_raw) and has_cache and (not stale_due_to_trading):
            if has_cache_price and has_cache_data_json:
                dbg.append("[policy] 非交易时段且已读到缓存（Save_Price + data_json）：IsTradingTime=False 以节省检索")
            elif has_cache_price:
                dbg.append("[policy] 非交易时段且已读到缓存（Save_Price）：IsTradingTime=False 以节省检索")
            else:
                dbg.append("[policy] 非交易时段且已读到缓存（data_json）：IsTradingTime=False 以节省检索")
        elif (not is_trading_time_raw) and has_cache and stale_due_to_trading:
            dbg.append("[policy] 非交易时段但缓存已过期（经历过交易时段）：IsTradingTime=True 以继续检索更新")

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


