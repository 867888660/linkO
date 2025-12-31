import json
import os
import copy
from datetime import datetime, timezone
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
try:
    # py3.9+
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

# -------------------------
# 调试开关与日志
# -------------------------
DEBUG_ENV = os.environ.get('ARRAY_POLY_DEBUG', '').strip() != ''

def _dbg(enabled, *args):
    # 精简旧日志：不再输出非 TRACE 前缀，避免噪声
    if not enabled:
        return
    try:
        print('[TRACE:ArrayPoly]', *args)
    except Exception:
        pass
 
def _trace(*args):
    # 统一的简洁 TRACE 打印（始终使用 TRACE 前缀，便于 workflow 过滤）
    try:
        print('[TRACE:ArrayPoly]', *args)
    except Exception:
        pass

# ================= 精度总控（改这里就能统一全局精度） =================
NDIGITS_PRICE = 6   # 价格/概率/比率类（0~1）
NDIGITS_USD   = 2   # 美元金额/深度/数量类（>=0）
# ====================================================================

# -------------------------
# 配置：输入 2 个（JSON 路径 + size限制），输出槽= 1(聚合Json_Save) + 字段清单长度
# -------------------------
InPutNum = 1

# 每个字段一个输出槽（顺序即表头）
FIELD_NAMES = [
    # 顶层字段
    'condition_id',
    'question',
    'endDate',
    'days_to_end',
    'rules',
    'resolutionSource',
    'url',

    # 规范化/辅助
    'option_name',
    'condition_id_ext',   # condition_id + '_' + slug(option_name)
    'ingested_at',        # UTC ISO 时间戳（生成时间）
    'source_file',        # 来源文件名（basename）

    # 盘口/价格
    'token',
    'ask',
    'bid',
    'l1_spread_c',
    'band_c_used',

    # 流动性/深度
    'depth_ask_1c_usd',
    'depth_bid_1c_usd',
    'depth_1c_usd',
    'depth_ask_1c_qty',
    'depth_bid_1c_qty',

    # 价带均价
    'vwap_ask_1c',
    'vwap_bid_1c',

    # 档位与集中度
    'n_orders_ask_1c',
    'n_orders_bid_1c',
    'top_concentration_ask_1c',
    'top_concentration_bid_1c',

    # 收益率
    'roi_if_win',
    'daily_eff_if_win',
    'apr_eff_if_win',
    'query_time_beijing',

    # 新增字段：务必追加在末尾，避免改变既有输出槽编号导致工作流"错位"
    'opp_token',
    # 钱包仓位兼容字段：务必追加在末尾
    'currentPrice',
    'currentValue',
    'size',  # 仓位大小/份额（兼容 size/shares/quantity/amount/balance）
    # ArrayTrigger 控制字段：是否为最后一条（布尔）
    'Islast',
]

# 额外 +1 个聚合输出槽：Json_Save
OutPutNum = len(FIELD_NAMES) + 1

# -------------------------
# 框架固定结构
# -------------------------
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

NodeKind = 'ArrayTrigger'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

# —— 按你要求，严格保留这个 FunctionIntroduction 字符串（不改动文案）——
FunctionIntroduction='组件功能：这是一个数组触发器节点，用于根据指定的数字范围生成包含输出节点序列的数组。\n\n代码功能摘要：接收起始和结束数字作为输入，通过循环遍历指定范围内的每个数字，为每个数字创建一个输出节点的深拷贝并存储到数组中，最终返回包含所有数字序列的数组。\n\n参数：\\n```yaml\\ninputs:\\n  - name: Input1\\n    type: integer\\n    required: true\\n    description: 数字范围的起始值\\n  - name: Input2\\n    type: integer\\n    required: true\\n    description: 数字范围的结束值（包含）\\noutputs:\\n  - name: OutPut1\\n    type: string\\n    description: 生成的数组序列，包含指定范围内所有数字对应的输出节点\\n```\n\n运行逻辑：\\n- 从输入节点获取起始数字Start_Num和结束数字End_Num\\n- 初始化空数组Array用于存储结果\\n- 使用for循环遍历从Start_Num到End_Num+1的范围（包含结束值）\\n- 在每次循环中，将当前数字i赋值给输出节点的Num属性\\n- 对当前输出节点进行深拷贝并添加到Array数组中\\n- 循环结束后返回包含所有数字序列的Array数组\\n- 每个数组元素都是一个完整的输出节点对象，包含对应的数字值'

# Inputs / Outputs 类型与命名
for i, input_def in enumerate(Inputs):
    input_def['Kind'] = 'String'
Inputs[0]['Kind'] = 'String_FilePath'
Inputs[0]['name'] = 'Js_FilePath'
Inputs[0]['Isnecessary'] = True
Inputs[0]['IsLabel'] = False


for i, out_def in enumerate(Outputs):
    if i == 0:
        out_def['name'] = 'Json_Save'   # 新增的聚合输出
        out_def['Kind'] = 'String'
    else:
        out_def['name'] = FIELD_NAMES[i - 1]   # 其它槽仍按字段命名
        # Islast 用 Boolean，其余保持 String
        out_def['Kind'] = 'Boolean' if out_def['name'] == 'Islast' else 'String'

# -------------------------
# 工具函数（兜底清洗）
# -------------------------
def _slugify(text: str) -> str:
    if text is None:
        return ''
    s = text.strip().lower()
    s = re.sub(r'\s+', '_', s)
    s = re.sub(r'[^a-z0-9_\-]', '', s)
    return s

def _s(val):
    return '' if val is None else str(val)

def _ensure_market_list(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if 'records' in data and isinstance(data['records'], list):
            return data['records']
        return [data]
    return []

def _get(d: dict, *keys, default=''):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] is not None:
            return d[k]
    return default

def _num(value, ndigits=NDIGITS_PRICE, lo=None, hi=None):
    """
    通用数值清洗：去逗号，支持科学计数法；非法/越界返回 ''。
    不处理百分号（专用 _pct01）。
    """
    if value is None:
        return ''
    s = str(value).strip()
    if s == '':
        return ''
    s = s.replace('，', ',').replace(',', '')
    try:
        x = Decimal(s)
    except InvalidOperation:
        return ''
    if not x.is_finite():
        return ''
    if lo is not None and x < Decimal(lo):
        return ''
    if hi is not None and x > Decimal(hi):
        return ''
    if ndigits is not None:
        q = Decimal(1).scaleb(-ndigits)
        x = x.quantize(q, rounding=ROUND_HALF_UP)
    return format(x.normalize(), 'f')

def _int_nonneg(value):
    """非负整数；非法返回 ''。"""
    if value is None:
        return ''
    s = str(value).strip()
    if s == '':
        return ''
    s = s.replace('，', ',').replace(',', '')
    try:
        x = int(Decimal(s).to_integral_value(rounding=ROUND_HALF_UP))
    except Exception:
        return ''
    if x < 0:
        return ''
    return str(x)

def _pct01(value, ndigits=NDIGITS_PRICE):
    """
    百分比/概率统一到 0~1，小数保留 ndigits。
    - 带 %/％ → 自动 /100
    - 无百分号：按原值（期望已是 0~1）；越界丢弃
    """
    if value is None:
        return ''
    raw = str(value).strip()
    if raw == '':
        return ''
    has_pct = ('%' in raw) or ('％' in raw)
    s = raw.replace('，', ',').replace(',', '').replace('％', '%').replace('%', '')
    try:
        x = Decimal(s)
    except InvalidOperation:
        return ''
    if not x.is_finite():
        return ''
    if has_pct:
        x = x / Decimal(100)
    if x < 0 or x > 1:
        return ''
    q = Decimal(1).scaleb(-ndigits)
    x = x.quantize(q, rounding=ROUND_HALF_UP)
    return format(x.normalize(), 'f')

def _pct_any(value, ndigits=NDIGITS_PRICE, allow_gt1=True):
    """
    百分比/概率转小数：可选是否允许 >1。
    - 带 %/％ → 自动 /100
    - 不带百分号：按原值
    - allow_gt1=True 时仅校验 x>=0；否则要求 0<=x<=1
    """
    if value is None:
        return ''
    raw = str(value).strip()
    if raw == '':
        return ''
    has_pct = ('%' in raw) or ('％' in raw)
    s = raw.replace('，', ',').replace(',', '').replace('％', '%').replace('%', '')
    try:
        x = Decimal(s)
    except InvalidOperation:
        return ''
    if not x.is_finite():
        return ''
    if has_pct:
        x = x / Decimal(100)
    if allow_gt1:
        if x < 0:
            return ''
    else:
        if x < 0 or x > 1:
            return ''
    q = Decimal(1).scaleb(-ndigits)
    x = x.quantize(q, rounding=ROUND_HALF_UP)
    return format(x.normalize(), 'f')

def _apr_from_daily(daily_str, ndigits=NDIGITS_PRICE, days=365):
    """当给定 APR 缺失时，由日化收益率反推年化（复利）。"""
    if daily_str is None:
        return ''
    s = str(daily_str).strip()
    if s == '':
        return ''
    try:
        d = Decimal(s)
    except Exception:
        return ''
    if not d.is_finite() or d < 0:
        return ''
    try:
        apr = (Decimal(1) + d) ** int(days) - Decimal(1)
    except Exception:
        return ''
    q = Decimal(1).scaleb(-ndigits)
    apr = apr.quantize(q, rounding=ROUND_HALF_UP)
    return format(apr.normalize(), 'f')

# -------------------------
# 时间/时区：days_to_end 统一修正
# -------------------------
def _parse_end_datetime(endDate_raw):
    """
    尽量把 endDate 解析成带 tzinfo 的 datetime。
    兼容：
    - 2025-12-25T12:34:56Z
    - 2025-12-25T12:34:56+00:00
    - 2025-12-25（视为当天 00:00:00）
    - 其它无法解析 → None
    """
    if endDate_raw is None:
        return None
    s = str(endDate_raw).strip()
    if not s:
        return None
    # 兼容 Z
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'
    # 仅日期
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', s):
        s = s + 'T00:00:00'
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    # 如果是 naive：默认按 UTC 解释（最保守，且避免“同日变负”）
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

def _calc_days_to_end(endDate_raw, now_utc=None, ndigits=4):
    """
    计算 days_to_end（保留 ndigits 位小数），并保证不为负：
    - endDate <= now → 0.0000
    - 其它 → round((end - now)/86400, ndigits)
    解析失败返回 ''（不覆盖原值）。
    """
    end_dt = _parse_end_datetime(endDate_raw)
    if end_dt is None:
        return ''
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    # 用 UTC 计算即可（时区转换不改变时间差）
    end_u = end_dt.astimezone(timezone.utc)
    now_u = now_utc.astimezone(timezone.utc)
    delta_seconds = (end_u - now_u).total_seconds()
    if delta_seconds <= 0:
        # 固定输出小数位，便于表格展示
        if ndigits <= 0:
            return '0'
        return '0.' + ('0' * int(ndigits))

    try:
        d = Decimal(str(delta_seconds)) / Decimal('86400')
        q = Decimal(1).scaleb(-int(ndigits))
        d = d.quantize(q, rounding=ROUND_HALF_UP)
        return format(d, 'f')
    except Exception:
        # 极端兜底
        val = delta_seconds / 86400.0
        if ndigits is None or ndigits <= 0:
            return str(int(val))
        return f"{val:.{int(ndigits)}f}"

def _is_negative_number(x):
    """
    判断是否为负数（支持 -0.3758 这类小数/字符串）。
    非法值返回 False（交由其它逻辑决定是否覆盖）。
    """
    if x is None:
        return False
    s = str(x).strip()
    if s == '':
        return False
    s = s.replace('，', ',').replace(',', '')
    try:
        v = Decimal(s)
    except Exception:
        return False
    if not v.is_finite():
        return False
    return v < 0

# -------------------------
# 主函数
# -------------------------
def run_node(node):
    # 支持两种方式开启调试：
    # 1) 调用时传入 node['Debug']=True
    # 2) 设置环境变量 ARRAY_POLY_DEBUG=1
    debug = False
    try:
        if isinstance(node, dict):
            debug = bool(node.get('Debug', False))
    except Exception:
        debug = False
    debug = debug or DEBUG_ENV

    Array = []
    all_records = []  # 用于 Json_Save 的聚合数组

    # 1) 读取输入文件路径和 size 参数
    json_path = node['Inputs'][0]['Context']

    if not json_path or not os.path.exists(json_path):
        _dbg(debug, 'early return: file path invalid or not exists')
        return Array

    # 2) 解析 JSON
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        _dbg(debug, 'json.load ok; type =', type(raw).__name__)
    except Exception as e:
        _dbg(debug, 'json.load failed:', repr(e))
        return Array

    markets = _ensure_market_list(raw)
    try:
        _dbg(debug, 'normalize to markets list; len =', len(markets))
    except Exception:
        _dbg(debug, 'normalize to markets list (non-list)')

    ingested_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
    source_file = os.path.basename(json_path)

    # 3) 遍历每个市场与其 options；若无 options，则按“扁平快照”处理
    idx_market = -1
    n_markets = 0
    n_options_total = 0
    n_flat_total = 0
    n_records_appended = 0
    for m in markets:
        idx_market += 1
        if not isinstance(m, dict):
            _dbg(debug, f'markets[{idx_market}] not dict, skip')
            continue

        # 公共字段（来自市场/扁平条目本身）
        condition_id = _get(m, 'condition_id')
        question = _get(m, 'question')
        endDate = _get(m, 'endDate')
        days_to_end = _get(m, 'days_to_end')
        rules = _get(m, 'rules')
        resolutionSource = _get(m, 'resolutionSource')
        url = _get(m, 'url')
        query_time_beijing = _get(m, 'query_time_beijing')

        # 统一重算 days_to_end（输出 4 位小数），并钳制到 >=0。
        # 这样你在“当天”看到的会是类似 0.3758 的剩余天数，而不是 0 或负数。
        calc_days = _calc_days_to_end(endDate, ndigits=4)
        if calc_days:
            # 若上游给了负数/整数/其它格式，这里统一覆盖为规范化小数
            if str(days_to_end).strip() != str(calc_days):
                _dbg(debug, f'normalize days_to_end: raw={days_to_end} -> calc={calc_days} (endDate={endDate})')
            days_to_end = calc_days

        options = m.get('options')
        options = options if isinstance(options, list) else None
        _dbg(debug,
             f'market[{idx_market}] cond={condition_id} options=',
             (len(options) if options is not None else 'None(flat)'))

        def build_record(src: dict):
            """从 option 或 扁平条目构造一条规范化记录"""
            option_name = _get(src, 'option_name', 'name')
            condition_id_ext = f"{condition_id}_{_slugify(option_name)}" if condition_id else _slugify(option_name)

            # 先计算日化与年化，避免清洗逻辑导致 APR 被丢弃
            daily_eff = _num(_get(src, 'daily_eff_if_win'), ndigits=NDIGITS_PRICE, lo=0, hi=1)
            apr_eff = _pct_any(_get(src, 'apr_eff_if_win'), ndigits=NDIGITS_PRICE, allow_gt1=True)
            if (not apr_eff) and daily_eff:
                apr_eff = _apr_from_daily(daily_eff)

            rec = {
                'condition_id': condition_id,
                'question': question,
                'endDate': endDate,
                'days_to_end': days_to_end,
                'rules': rules,
                'resolutionSource': resolutionSource,
                'url': url,

                'option_name': option_name,
                'condition_id_ext': condition_id_ext,
                'ingested_at': ingested_at,
                'source_file': source_file,

                # 盘口/价格（0~1）
                'token': _get(src, 'token'),
                'opp_token': _get(src, 'opp_token'),
                'ask': _num(_get(src, 'ask'), ndigits=NDIGITS_PRICE, lo=0, hi=1),
                'bid': _num(_get(src, 'bid'), ndigits=NDIGITS_PRICE, lo=0, hi=1),
                # 钱包仓位字段（兼容 PolyMarket_WalletPositions_BatchSave.py）
                # currentPrice：0~1；优先 currentPrice，其次 current_price；再其次用 ask/bid 的值
                'currentPrice': _num(_get(src, 'currentPrice', 'current_price', 'curPrice', 'cur_price', 'ask'), ndigits=NDIGITS_PRICE, lo=0, hi=1),
                # currentValue：USD 金额（>=0）；兼容 currentValue / CUR_VALUE / value
                'currentValue': _num(_get(src, 'currentValue', 'current_value', 'CUR_VALUE', 'curValue', 'cur_value', 'value'), ndigits=NDIGITS_USD, lo=0),
                # size：仓位大小/份额（>=0）；兼容 size / shares / quantity / amount / balance
                'size': _num(_get(src, 'size', 'shares', 'quantity', 'amount', 'balance'), ndigits=NDIGITS_USD, lo=0),
                # ArrayTrigger 控制字段：默认 false，最后一条会在循环结束后统一置 true
                'Islast': False,
                # 价差（单位：美分），来源通常是整数 0,1,2,... 不能按 0~1 概率清洗
                'l1_spread_c': _int_nonneg(_get(src, 'l1_spread_c')),
                'band_c_used': _s(_get(src, 'band_c_used')),

                # 深度/数量（非负）
                'depth_ask_1c_usd': _num(_get(src, 'depth_ask_1c_usd'), ndigits=NDIGITS_USD, lo=0),
                'depth_bid_1c_usd': _num(_get(src, 'depth_bid_1c_usd'), ndigits=NDIGITS_USD, lo=0),
                'depth_1c_usd': _num(_get(src, 'depth_1c_usd'), ndigits=NDIGITS_USD, lo=0),
                'depth_ask_1c_qty': _num(_get(src, 'depth_ask_1c_qty'), ndigits=NDIGITS_USD, lo=0),
                'depth_bid_1c_qty': _num(_get(src, 'depth_bid_1c_qty'), ndigits=NDIGITS_USD, lo=0),

                # 均价（0~1）
                'vwap_ask_1c': _num(_get(src, 'vwap_ask_1c'), ndigits=NDIGITS_PRICE, lo=0, hi=1),
                'vwap_bid_1c': _num(_get(src, 'vwap_bid_1c'), ndigits=NDIGITS_PRICE, lo=0, hi=1),

                # 档位与集中度（0~1；订单数为非负整数）
                'n_orders_ask_1c': _int_nonneg(_get(src, 'n_orders_ask_1c')),
                'n_orders_bid_1c': _int_nonneg(_get(src, 'n_orders_bid_1c')),
                'top_concentration_ask_1c': _num(_get(src, 'top_concentration_ask_1c'), ndigits=NDIGITS_PRICE, lo=0, hi=1),
                'top_concentration_bid_1c': _num(_get(src, 'top_concentration_bid_1c'), ndigits=NDIGITS_PRICE, lo=0, hi=1),

                # 收益/效率（统一 0~1；apr 支持带 %）
                'roi_if_win': _num(_get(src, 'roi_if_win'), ndigits=NDIGITS_PRICE, lo=0, hi=1),
                'daily_eff_if_win': daily_eff,
                'apr_eff_if_win': apr_eff,

                'query_time_beijing': query_time_beijing,
            }
            # 仅保留定义字段，避免脏键
            return {k: rec.get(k, '') for k in FIELD_NAMES}

        if options:
            # 结构：market + options[]
            for j, opt in enumerate(options):
                if not isinstance(opt, dict):
                    _dbg(debug, f'  option[{j}] not dict, skip')
                    continue
                try:
                    record = build_record(opt)
                except Exception as e:
                    _dbg(debug, f'  build_record option[{j}] failed:', repr(e))
                    continue
                all_records.append(record)
                n_options_total += 1
                n_records_appended += 1
                # 分步关键日志：每条记录都给出简短信息（便于定位为何出现 32 条）
                _dbg(debug, f'  +append opt[{j}] -> condition_id_ext={record.get("condition_id_ext","")} ask={record.get("ask","")} bid={record.get("bid","")}')

                row = copy.deepcopy(Outputs)
                row[0]['Context'] = ''  # Json_Save 循环后统一填
                for i, field in enumerate(FIELD_NAMES, start=1):
                    if field == 'Islast':
                        row[i]['Boolean'] = False
                        row[i]['Context'] = ''  # Boolean 类型不依赖 Context
                    else:
                        row[i]['Context'] = _s(record.get(field, ''))
                Array.append(row)
        else:
            # 扁平结构：每条条目本身就是一个“option 快照”
            try:
                record = build_record(m)
            except Exception as e:
                _dbg(debug, f'  build_record flat failed:', repr(e))
                continue
            all_records.append(record)
            n_flat_total += 1
            n_records_appended += 1
            _dbg(debug, f'  +append flat -> condition_id_ext={record.get("condition_id_ext","")} ask={record.get("ask","")} bid={record.get("bid","")}')

            row = copy.deepcopy(Outputs)
            row[0]['Context'] = ''  # Json_Save 循环后统一填
            for i, field in enumerate(FIELD_NAMES, start=1):
                if field == 'Islast':
                    row[i]['Boolean'] = False
                    row[i]['Context'] = ''
                else:
                    row[i]['Context'] = _s(record.get(field, ''))
            Array.append(row)

        n_markets += 1

    original_count = len(Array)
    # 5) 生成整批 Json，一次性字符串，回填到每条记录的 Json_Save 槽
    try:
        json_save_str = json.dumps(all_records, ensure_ascii=False)
        _dbg(debug, 'json.dumps(all_records) ok; records =', len(all_records))
    except Exception:
        # 极端兜底：不可序列化对象转字符串
        def _safe(v):
            try:
                json.dumps(v)
                return v
            except Exception:
                return str(v)
        safe_records = [{k: _safe(v) for k, v in rec.items()} for rec in all_records]
        json_save_str = json.dumps(safe_records, ensure_ascii=False)

    for row in Array:
        row[0]['Context'] = json_save_str

    # 6) 设置 Islast：仅最后一条为 True
    try:
        islast_idx = None
        for idx, out_def in enumerate(Outputs):
            if out_def.get('name') == 'Islast':
                islast_idx = idx
                break
        if islast_idx is not None and Array:
            # 先全部置 False
            for r in Array:
                try:
                    r[islast_idx]['Boolean'] = False
                    r[islast_idx]['Context'] = ''
                except Exception:
                    pass
            # 最后一条置 True
            try:
                Array[-1][islast_idx]['Boolean'] = True
                Array[-1][islast_idx]['Context'] = ''
            except Exception:
                pass
    except Exception:
        pass

    # 收尾关键信息：本次输出条目数（Array 长度）与记录数
    _dbg(debug,
         'done.',
         'markets =', n_markets,
         'options_total =', n_options_total,
         'flats_total =', n_flat_total,
         'records_appended =', n_records_appended,
         'original_rows =', original_count,
         'final_rows =', len(Array)
         )
    # === 返回值兜底：保证二维数组形状 ===
    def _looks_like_output_slot(x):
        return isinstance(x, dict) and isinstance(x.get('Id'), str) and x['Id'].startswith('Output')
    if not isinstance(Array, list):
        Array = []
    elif Array and isinstance(Array[0], dict) and _looks_like_output_slot(Array[0]):
        # 说明误返回了“单行的 Outputs”
        Array = [Array]
    return Array
