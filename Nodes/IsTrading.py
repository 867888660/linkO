import re
import copy
from datetime import datetime, timezone, timedelta, date


# =========================
# Node metadata
# =========================
OutPutNum = 1
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
        'Num': None, 'Kind': None, 'Boolean': False,
        'Id': f'Input{i + 1}', 'Context': None,
        'Isnecessary': True, 'name': f'Input{i + 1}',
        'Link': 0, 'IsLabel': False
    }
    for i in range(InPutNum)
]

NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# --- 输入：当前时间 ---
Inputs[0]['Kind'] = 'String'
Inputs[0]['name'] = 'NowTime'
Inputs[0]['Isnecessary'] = True

# --- 输出：是否在交易时间 ---
Outputs[0]['Kind'] = 'Boolean'
Outputs[0]['name'] = 'IsTrading'
Outputs[0]['Description'] = '是否在美股常规交易时间（美东 周一~周五 09:30-16:00，排除节假日，自动处理夏令时/冬令时）'

FunctionIntroduction = (
    '组件功能：判断当前是否处于美股常规交易时间。\n\n'
    '判定规则：\n'
    '  - 美东时间 周一~周五 09:30:00 <= t < 16:00:00 为交易时段\n'
    '  - 自动处理夏令时（EDT，UTC-4）与冬令时（EST，UTC-5）切换\n'
    '    · 夏令时：3 月第二个周日 02:00 本地时间开始\n'
    '    · 冬令时：11 月第一个周日 02:00 本地时间开始\n'
    '  - 周末（周六、周日）不交易\n'
    '  - 排除 NYSE/Nasdaq 全日休市日：\n'
    '    · New Year\'s Day（1/1 observed）\n'
    '    · Martin Luther King Jr. Day（1 月第三个周一）\n'
    '    · Presidents\' Day（2 月第三个周一）\n'
    '    · Good Friday（复活节前的周五）\n'
    '    · Memorial Day（5 月最后一个周一）\n'
    '    · Juneteenth（6/19 observed，2022 年起）\n'
    '    · Independence Day（7/4 observed）\n'
    '    · Labor Day（9 月第一个周一）\n'
    '    · Thanksgiving Day（11 月第四个周四）\n'
    '    · Christmas Day（12/25 observed）\n\n'
    '参数\n```yaml\n'
    'inputs:\n'
    '  - name: NowTime\n'
    '    type: string\n'
    '    required: true\n'
    '    description: UTC 时间字符串（如 2026-03-04T15:30:00Z），支持多种格式；为空则自动取当前 UTC 时间\n'
    'outputs:\n'
    '  - name: IsTrading\n'
    '    type: boolean\n'
    '    description: True=当前在美股常规交易时段，False=不在\n'
    '```\n'
)


# =========================================================================
# 时间工具函数
# =========================================================================

def _safe_str(x) -> str:
    try:
        return '' if x is None else str(x)
    except Exception:
        return ''


def _clean_and_parse_time(raw) -> datetime:
    """
    解析时间字符串，支持多种格式：
    - 2026-03-04T15:30:00Z
    - 2026-03-04 15:30:00
    - 2026-03-04（仅日期，默认午夜 UTC）
    - 月/日可不补零：2026-3-4T14:00:00Z
    若缺省时区，默认按 UTC 处理。
    """
    s = _safe_str(raw).strip().strip('"').strip("'").strip()
    if not s:
        return datetime.now(timezone.utc)

    # 兼容空格分隔
    if ' ' in s and 'T' not in s:
        parts = s.split()
        if len(parts) >= 2:
            s = parts[0] + 'T' + parts[1]

    # 补齐月日为两位
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})(.*)$', s)
    if m:
        y, mo, d, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        s = f'{y}-{int(mo):02d}-{int(d):02d}{rest}'

    # 仅日期 → 补午夜 UTC
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', s):
        s = s + 'T00:00:00+00:00'

    # Z → +00:00
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'

    # 无时区 → 按 UTC
    has_time = 'T' in s
    has_tz = bool(re.search(r'([+-]\d{2}:\d{2})$', s))
    if has_time and not has_tz:
        s = s + '+00:00'

    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# =========================================================================
# 日期计算工具
# =========================================================================

def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """返回某年某月第 n 个 weekday 的日期。weekday: Monday=0 … Sunday=6"""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    day = 1 + offset + (n - 1) * 7
    return date(year, month, day)


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """返回某年某月最后一个 weekday 的日期。"""
    if month == 12:
        first_next = date(year + 1, 1, 1)
    else:
        first_next = date(year, month + 1, 1)
    cur = first_next - timedelta(days=1)
    while cur.weekday() != weekday:
        cur -= timedelta(days=1)
    return cur


def _easter_sunday(year: int) -> date:
    """公历复活节日期（Meeus/Jones/Butcher 算法）。"""
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
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = ((h + l_ - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _observed(d: date) -> date:
    """
    固定日期假期的 observed 规则：
    - 周六 → 提前到周五
    - 周日 → 顺延到周一
    """
    wd = d.weekday()
    if wd == 5:
        return d - timedelta(days=1)
    if wd == 6:
        return d + timedelta(days=1)
    return d


# =========================================================================
# 美股假日
# =========================================================================

def _us_market_holidays(year: int) -> set:
    """
    NYSE/Nasdaq 全日休市日（按美东本地日期）。
    覆盖每年常规固定/规则假期，不含历史性一次性停市。
    """
    hol = set()

    # New Year's Day (Jan 1 observed)
    hol.add(_observed(date(year, 1, 1)))

    # Martin Luther King Jr. Day: 1 月第三个周一
    hol.add(_nth_weekday_of_month(year, 1, 0, 3))

    # Presidents' Day (Washington's Birthday): 2 月第三个周一
    hol.add(_nth_weekday_of_month(year, 2, 0, 3))

    # Good Friday: 复活节前两天（周五）
    hol.add(_easter_sunday(year) - timedelta(days=2))

    # Memorial Day: 5 月最后一个周一
    hol.add(_last_weekday_of_month(year, 5, 0))

    # Juneteenth: 6/19 observed（NYSE 自 2022 年起休市）
    if year >= 2022:
        hol.add(_observed(date(year, 6, 19)))

    # Independence Day: 7/4 observed
    hol.add(_observed(date(year, 7, 4)))

    # Labor Day: 9 月第一个周一
    hol.add(_nth_weekday_of_month(year, 9, 0, 1))

    # Thanksgiving Day: 11 月第四个周四
    hol.add(_nth_weekday_of_month(year, 11, 3, 4))

    # Christmas Day: 12/25 observed
    hol.add(_observed(date(year, 12, 25)))

    # 仅保留当年日期（避免 1/1 周六 observed 变成上年 12/31）
    return {d for d in hol if d.year == year}


def _is_holiday(local_d: date) -> bool:
    """判断美东本地日期是否为休市日（含跨年 observed）。"""
    hol = set()
    hol |= _us_market_holidays(local_d.year - 1)
    hol |= _us_market_holidays(local_d.year)
    hol |= _us_market_holidays(local_d.year + 1)
    return local_d in hol


# =========================================================================
# 夏令时 / 冬令时
# =========================================================================

def _dst_start_end(year: int):
    """
    美国东部夏令时（DST）窗口：
    - 开始：3 月第二个周日 02:00 EST → UTC 07:00
    - 结束：11 月第一个周日 02:00 EDT → UTC 06:00
    返回 (start_utc, end_utc)
    """
    dst_start_day = _nth_weekday_of_month(year, 3, 6, 2)   # 3 月第二个周日
    dst_end_day = _nth_weekday_of_month(year, 11, 6, 1)     # 11 月第一个周日
    start_utc = datetime(year, 3, dst_start_day.day, 7, 0, 0, tzinfo=timezone.utc)
    end_utc = datetime(year, 11, dst_end_day.day, 6, 0, 0, tzinfo=timezone.utc)
    return start_utc, end_utc


def _eastern_offset(dt_utc: datetime) -> int:
    """返回美东相对 UTC 的小时偏移：EDT=-4, EST=-5。"""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    else:
        dt_utc = dt_utc.astimezone(timezone.utc)
    start_utc, end_utc = _dst_start_end(dt_utc.year)
    return -4 if (start_utc <= dt_utc < end_utc) else -5


# =========================================================================
# 核心判定
# =========================================================================

def _is_us_regular_trading_time(dt_utc: datetime) -> bool:
    """
    判定是否在美股常规交易时段：
    美东 周一~周五 09:30:00 <= t < 16:00:00
    排除节假日。
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    dt_utc = dt_utc.astimezone(timezone.utc)

    offset_h = _eastern_offset(dt_utc)
    dt_et = dt_utc + timedelta(hours=offset_h)

    # 周末
    if dt_et.weekday() >= 5:
        return False

    # 节假日
    if _is_holiday(dt_et.date()):
        return False

    # 交易时段 09:30 <= t < 16:00
    t = dt_et.time()
    return (t.hour > 9 or (t.hour == 9 and t.minute >= 30)) and (t.hour < 16)


# =========================================================================
# 节点入口
# =========================================================================

def run_node(node):
    try:
        inps = node.get('Inputs') or []
        raw = ((inps[0] if len(inps) > 0 else {}) or {}).get('Context')
        if raw is None:
            raw = ((inps[0] if len(inps) > 0 else {}) or {}).get('Num')

        dt_utc = _clean_and_parse_time(raw).astimezone(timezone.utc)
        trading = bool(_is_us_regular_trading_time(dt_utc))

        Outputs[0]['Boolean'] = trading
        Outputs[0]['Context'] = 'True' if trading else 'False'
        return copy.deepcopy(Outputs)

    except Exception as e:
        Outputs[0]['Boolean'] = False
        Outputs[0]['Context'] = f'Error: {e}'
        return copy.deepcopy(Outputs)
