import json
import os
import copy
import time
import random
from datetime import datetime
from typing import Dict, Any, List, Iterable
import requests
import math
import re
from datetime import timezone
from datetime import timedelta

# 全局会话，带 UA 提高稳定性
SESS = requests.Session()
SESS.headers.update({"User-Agent": "pm-screen/1.0"})

# 缓存 zoneinfo 导入（避免循环中重复导入）
_ZONEINFO_CACHE = None
try:
    from zoneinfo import ZoneInfo
    _ZONEINFO_CACHE = ZoneInfo
except ImportError:
    _ZONEINFO_CACHE = None

# **Define the number of outputs and inputs**
OutPutNum = 2
InPutNum = 8  # limit, offset_start, closed, retry, save_path, offset_end, category_filter, event_id
# **Define the number of outputs and inputs**

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs  = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}',  'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}',  'Link': 0, 'IsLabel': True} for i in range(InPutNum)]
# **Initialize Outputs and Inputs arrays and assign names directly**

NodeKind = 'passivityTrigger'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction = (
    '组件功能（简述代码整体功能）\n'
    '这是一个Polymarket市场数据抓取节点：输入分页参数、保存路径和类别过滤条件，调用Polymarket Gamma API（/markets）逐页抓取市场列表，提取核心字段（question、rules、endDate、category等），每页处理完成后单独保存为JSON文件，输出保存路径和调试信息。\n\n'
    '代码功能摘要（概括核心算法或主要处理步骤）\n'
    '程序读取输入的分页参数（limit、offset_start、offset_end）、closed标志、重试次数、保存路径和类别过滤条件，'
    '调用Polymarket Gamma API的/markets接口获取市场列表数据，'
    '对于缺失字段的市场，通过详情页接口补充完整信息，'
    '解析并标准化endDate字段（优先使用CLOB接口的end_date_iso，其次解析rules文本中的时间，最后使用Gamma的endDate），'
    '将处理后的数据保存为JSON文件，'
    '通过node._state.next_offset记忆续跑位置实现分页处理，每次调用仅处理一页数据。\n\n'
    '参数\n```yaml\n'
    'inputs:\n'
    '  - name: limit\n    type: number\n    required: true\n    description: 每页抓取数量，例如 100\n'
    '  - name: offset_start\n    type: number\n    required: true\n    description: 起始偏移量，例如 0\n'
    '  - name: closed\n    type: boolean\n    required: true\n    description: 是否包含已关闭的市场，false表示仅开放市场\n'
    '  - name: retry\n    type: number\n    required: true\n    description: 请求失败时的重试次数，例如 1\n'
    '  - name: save_path\n    type: string\n    required: true\n    description: JSON文件保存路径，例如 "./output"\n'
    '  - name: offset_end\n    type: number\n    required: true\n    description: 结束偏移量，-1为无上限模式（遇尾页暂停），>0为边界模式（递增至该值后停止）\n'
    '  - name: category_filter\n    type: string\n    required: true\n    description: 类别过滤，"All"表示全部类别，或指定tag_id/tag slug/tag label\n'
    '  - name: event_id\n    type: string\n    required: false\n    description: 事件ID（EventId），来自 Gamma Events API 的 event.id；为空/All 表示不过滤\n'
    'outputs:\n'
    '  - name: Save_Path\n    type: string\n    description: 保存的JSON文件完整路径\n'
    '  - name: DeBug\n    type: string\n    description: 调试信息，包含配置参数、抓取数量、处理状态等\n```\n'
    '\n运行逻辑（用 - 列表描写详细流程）\n'
    '- 读取Input1作为limit（每页数量）\n'
    '- 读取Input2作为offset_start（起始偏移量）\n'
    '- 读取Input3作为closed（是否包含已关闭市场）\n'
    '- 读取Input4作为retry（重试次数）\n'
    '- 读取Input5作为save_path（保存路径），若不存在则创建目录\n'
    '- 读取Input6作为offset_end（结束偏移量）\n'
    '- 读取Input7作为category_filter（类别过滤），解析为tag_id（支持"All"、数字ID、tag slug/label）\n'
    '- 从node._state.next_offset获取当前偏移量（首次使用offset_start）\n'
    '- 调用Polymarket Gamma API /markets接口获取市场列表（带tag_id过滤）\n'
    '- 从列表页提取基础信息（question、rules、endDate、category等）\n'
    '- 对于缺失字段的市场，调用详情页接口补充完整信息\n'
    '- 解析endDate：优先使用CLOB接口的end_date_iso，其次解析rules文本中的美东时间，最后使用Gamma的endDate，若为midnight UTC则按规则修正为ET时间点\n'
    '- 计算days_to_end（距离结束日期的天数）\n'
    '- 添加元信息（query_time_beijing、offset、url）\n'
    '- 将处理后的数据保存为JSON文件（每页一个文件）\n'
    '- 更新node._state.next_offset为下一页偏移量\n'
    '- 输出Save_Path（文件路径）和DeBug（调试信息）'
)

# =====================
# 严格逐行设置入/出参属性（极简模式：仅核心字段）
# =====================

Inputs[0]['Kind'] = 'Num'
Inputs[0]['name'] = 'limit'
Inputs[0]['Isnecessary'] = True
Inputs[0]['IsLabel'] = True
Inputs[0]['Num'] = 200

Inputs[1]['Kind'] = 'Num'
Inputs[1]['name'] = 'offset_start'
Inputs[1]['Isnecessary'] = True
Inputs[1]['IsLabel'] = True
Inputs[1]['Num'] = 0

Inputs[2]['Kind'] = 'Boolean'
Inputs[2]['name'] = 'closed'
Inputs[2]['Isnecessary'] = True
Inputs[2]['IsLabel'] = True
Inputs[2]['Boolean'] = False

Inputs[3]['Kind'] = 'Num'
Inputs[3]['name'] = 'retry'
Inputs[3]['Isnecessary'] = True
Inputs[3]['IsLabel'] = True
Inputs[3]['Num'] = 1

Inputs[4]['Kind'] = 'String_FilePath'
Inputs[4]['name'] = 'save_path'
Inputs[4]['Isnecessary'] = True
Inputs[4]['IsLabel'] = True

Inputs[5]['Kind'] = 'Num'
Inputs[5]['name'] = 'offset_end'
Inputs[5]['Isnecessary'] = True
Inputs[5]['IsLabel'] = True
Inputs[5]['Num'] = -1

Inputs[6]['Kind'] = 'String'
Inputs[6]['name'] = 'category_filter'
Inputs[6]['Isnecessary'] = True
Inputs[6]['IsLabel'] = True
Inputs[6]['Context'] = 'All'  # 类别/分区（tag_id 或 tag slug/label；All 表示不过滤）

Inputs[7]['Kind'] = 'String'
Inputs[7]['name'] = 'event_id'
Inputs[7]['Isnecessary'] = False
Inputs[7]['IsLabel'] = True
Inputs[7]['Context'] = ''  # EventId（Gamma Events API 的 event.id）；空/All 表示不过滤

Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Save_Path'

Outputs[1]['Kind'] = 'String'
Outputs[1]['name'] = 'DeBug'

# =====================
# Polymarket API 工具
# =====================
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

def _backoff_sleep(attempt: int):
    time.sleep((2 ** attempt) * 0.2 + random.random() * 0.3)

def robust_get(url: str, params: Dict[str, Any] = None, retry: int = 2, timeout: int = 12) -> Any:
    for k in range(retry + 1):
        try:
            r = SESS.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        _backoff_sleep(k)
    raise RuntimeError(f"GET 失败: {url} params={params}")

def try_get_clob_end_date_iso(condition_id: str, retry: int = 1) -> (str, str):
    """
    返回 (end_date_iso, err)
    - 成功：("2026-03-31T00:00:00Z", "")
    - 失败：("", "原因")
    """
    cid = str(condition_id or "").strip()
    if not (cid.startswith("0x") and len(cid) == 66):
        return "", f"invalid_condition_id={cid}"

    try:
        data = robust_get(f"{CLOB}/markets/{cid}", params=None, retry=retry, timeout=10)
        m = data.get("market") if isinstance(data, dict) and isinstance(data.get("market"), dict) else data
        if isinstance(m, dict):
            end_iso = m.get("end_date_iso") or m.get("endDate") or ""
        else:
            end_iso = ""
        if not end_iso:
            return "", "clob_end_date_iso_missing"
        return str(end_iso), ""
    except Exception as e:
        return "", f"clob_end_date_iso_fetch_fail:{type(e).__name__}"

def robust_post(url: str, json_body: Dict[str, Any], retry: int = 2, timeout: int = 12) -> Any:
    for k in range(retry + 1):
        try:
            r = SESS.post(url, json=json_body, timeout=timeout)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        _backoff_sleep(k)
    raise RuntimeError(f"POST 失败: {url} body_keys={list(json_body.keys())}")

def _resolve_tag_id(category_filter: str, session: requests.Session, debug_lines: List[str] = None) -> int | None:
    """
    category_filter:
      - 'ALL' / '' => None
      - '12345'    => 12345
      - 'politics' / 'Politics' / 'sports' / tag label => lookup once via /tags
    """
    cf = (category_filter or "").strip()
    if not cf or cf.upper() == "ALL":
        return None
    if cf.isdigit():
        return int(cf)

    # lookup tag by slug or label (case-insensitive), cached on session
    cache_key = "_pm_tags_cache"
    if not hasattr(session, cache_key):
        try:
            r = session.get("https://gamma-api.polymarket.com/tags", timeout=10)
            r.raise_for_status()
            tags_data = r.json() or []
            setattr(session, cache_key, tags_data)
            if debug_lines is not None:
                debug_lines.append(f"tags_api_fetched: {len(tags_data)} tags")
        except Exception as e:
            if debug_lines is not None:
                debug_lines.append(f"tags_api_fetch_fail: {type(e).__name__}")
            return None

    tags = getattr(session, cache_key)
    cf_l = cf.lower()
    
    # 精确匹配
    for t in tags:
        slug = str(t.get("slug") or "").lower()
        label = str(t.get("label") or "").lower()
        if cf_l == slug or cf_l == label:
            tid = t.get("id")
            tag_id = int(tid) if str(tid).isdigit() else None
            if debug_lines is not None and tag_id:
                debug_lines.append(f"tag_found_exact: '{cf}' -> id={tag_id} (slug='{slug}', label='{label}')")
            return tag_id
    
    # 部分匹配（如果精确匹配失败）
    for t in tags:
        slug = str(t.get("slug") or "").lower()
        label = str(t.get("label") or "").lower()
        if cf_l in slug or cf_l in label or slug in cf_l or label in cf_l:
            tid = t.get("id")
            tag_id = int(tid) if str(tid).isdigit() else None
            if debug_lines is not None and tag_id:
                debug_lines.append(f"tag_found_partial: '{cf}' -> id={tag_id} (slug='{slug}', label='{label}')")
            return tag_id

    # 没找到
    if debug_lines is not None:
        # 列出前几个可用的 tags 供参考
        sample_tags = [f"{t.get('label', '')}({t.get('slug', '')})" for t in tags[:5]]
        debug_lines.append(f"tag_not_found: '{cf}' (available samples: {', '.join(sample_tags)})")
    return None

def _normalize_event_id(event_id: str) -> str:
    s = (event_id or "").strip()
    if not s or s.upper() == "ALL":
        return ""
    return s

def _extract_event_id_from_market_stub(stub: Dict[str, Any]) -> str:
    """
    从 market stub 中尽可能提取 event_id。
    兼容字段：
    - event_id / eventId
    - events: [{id: ...}, ...] 或 ["id", ...]
    """
    if not isinstance(stub, dict):
        return ""
    for k in ("event_id", "eventId", "eventID", "EventID"):
        v = stub.get(k)
        if v:
            return str(v).strip()
    evs = stub.get("events")
    if isinstance(evs, list) and evs:
        first = evs[0]
        if isinstance(first, dict) and first.get("id"):
            return str(first.get("id")).strip()
        if isinstance(first, str):
            return first.strip()
    return ""

def fetch_markets(limit: int, offset: int, closed: bool, retry: int, category_filter: str = "ALL", event_id: str = "", debug_lines: List[str] = None) -> List[Dict[str, Any]]:
    params = {
        "limit": limit,
        "offset": offset,
        "closed": str(closed).lower(),
        "withTokens": "true",
        "withClobTokenIds": "true",
        "withOutcomes": "true"
    }

    # ✅ 新增：按 EventID 过滤（Gamma Events API 的 event.id）
    eid = _normalize_event_id(event_id)
    if eid:
        # 优先用 /events/{id}（官方定义：events contain their associated markets）
        try:
            ev = robust_get(f"{GAMMA}/events/{eid}", params=None, retry=max(1, retry), timeout=12)
            markets = None
            if isinstance(ev, dict):
                if isinstance(ev.get("markets"), list):
                    markets = ev.get("markets")
                elif isinstance(ev.get("data"), dict) and isinstance(ev["data"].get("markets"), list):
                    markets = ev["data"].get("markets")
                elif isinstance(ev.get("event"), dict) and isinstance(ev["event"].get("markets"), list):
                    markets = ev["event"].get("markets")
            if markets is not None:
                # closed 过滤（若字段存在）
                if closed is False:
                    markets = [m for m in markets if not bool((m or {}).get("closed", False))] if isinstance(markets, list) else markets
                # 做一次与 /markets 一致的“分页切片”
                page = markets[int(offset): int(offset) + int(limit)] if isinstance(markets, list) else []
                if debug_lines is not None:
                    debug_lines.append(f"event_markets_mode: event_id={eid}, total={len(markets) if isinstance(markets, list) else 'n/a'}, page={len(page)}")
                return page
        except Exception as e:
            if debug_lines is not None:
                debug_lines.append(f"event_markets_mode_fail: {type(e).__name__} -> fallback_to_markets_api")

        # 兜底：在 /markets 查询侧尝试 event_id 过滤（若后端支持）
        params["event_id"] = eid
        if debug_lines is not None:
            debug_lines.append(f"filter_applied: event_id={eid} (markets_api_fallback)")

    # ✅ 改：用 tag_id 在请求端过滤（更快、更符合官方）
    tag_id = _resolve_tag_id(category_filter, SESS, debug_lines=debug_lines)
    if tag_id is not None:
        params["tag_id"] = tag_id
        params["related_tags"] = "true"   # 官方支持 related_tags 参数
        if debug_lines is not None:
            debug_lines.append(f"filter_applied: tag_id={tag_id} for category_filter='{category_filter}'")
    else:
        if debug_lines is not None and category_filter and category_filter.upper() != "ALL":
            debug_lines.append(f"filter_not_applied: category_filter='{category_filter}' (tag_id not found)")
    
    data = robust_get(f"{GAMMA}/markets", params=params, retry=retry)
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
        return data["data"]
    if isinstance(data, list):
        return data
    return []

def ensure_dir(path: str):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def autogen_filename() -> str:
    return f"polymarket_json_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

def _parse_end_ts_safe(end_date_str: str) -> float:
    """将 ISO8601 time 转 UTC 时间戳，容错 Z / +00:00 / 无 tz 的情况。失败返回 0."""
    if not end_date_str:
        return 0.0
    try:
        s = end_date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0

_GAMMA_MIDNIGHT_UTC_RE = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})T00:00:00(?:Z|\+00:00)\s*$")

def _rules_hint_et_noon(rules: str) -> bool:
    """
    判断 rules 是否暗示"美东当天 12:00（noon）"这种结算时间。
    典型文本：
    - '... 12:00 in the ET timezone (noon) on the date specified in the title ...'
    """
    if not rules:
        return False
    txt = _normalize_rules(str(rules))
    t = txt.lower()
    # 同时满足：出现 12:00、出现 ET、并且出现 noon 或 'et timezone'
    has_1200 = "12:00" in t
    has_et = (" et " in f" {t} ") or ("et timezone" in t)
    has_noon = "noon" in t
    return bool(has_1200 and has_et and (has_noon or "et timezone" in t))

def _ny_is_dst_local(year: int, month: int, day: int, hour: int, minute: int, second: int) -> bool:
    """
    无 zoneinfo 时，按美国纽约 DST 规则判断（2007+ 规则）：
    - DST 开始：3 月第二个周日 02:00
    - DST 结束：11 月第一个周日 02:00
    """
    try:
        dt = datetime(year, month, day, hour, minute, second)
    except Exception:
        return False

    def _nth_sunday(y: int, m: int, n: int) -> int:
        first = datetime(y, m, 1)
        # Python weekday: Mon=0 ... Sun=6
        delta = (6 - first.weekday()) % 7
        return 1 + delta + 7 * (n - 1)

    # 边界日期
    dst_start_day = _nth_sunday(year, 3, 2)   # 3月第二个周日
    dst_end_day   = _nth_sunday(year, 11, 1)  # 11月第一个周日

    dst_start = datetime(year, 3, dst_start_day, 2, 0, 0)
    dst_end   = datetime(year, 11, dst_end_day, 2, 0, 0)
    return dst_start <= dt < dst_end

def _normalize_midnight_utc_to_et_time(end_date_str: str, rules: str = "") -> (str, str):
    """
    将 'YYYY-MM-DDT00:00:00Z'（看起来像"日期占位"）修正为更贴近真实结算的美东时间点：
    - 若 rules 暗示 noon：用 ET 12:00:00
    - 否则兜底：用 ET 23:59:59（EOD）
    返回 (utc_iso, label)：
    - utc_iso: 修正后的 UTC ISO（Z）；不满足条件返回 ""
    - label: "noon" 或 "eod"
    """
    if not end_date_str:
        return "", ""
    m = _GAMMA_MIDNIGHT_UTC_RE.match(str(end_date_str))
    if not m:
        return "", ""
    try:
        y = int(m.group(1)); mo = int(m.group(2)); d = int(m.group(3))
    except Exception:
        return "", ""

    # 选择 ET 时间点
    is_noon = _rules_hint_et_noon(rules)
    hh = 12 if is_noon else 23
    minute = 0 if is_noon else 59
    second = 0 if is_noon else 59
    label = "noon" if is_noon else "eod"

    # 优先用 zoneinfo 精确处理 DST（America/New_York）
    if _ZONEINFO_CACHE is not None:
        try:
            dt_local = datetime(y, mo, d, hh, minute, second, tzinfo=_ZONEINFO_CACHE("America/New_York"))
            dt_utc = dt_local.astimezone(timezone.utc)
            return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), label
        except Exception:
            pass
    # 兜底：按规则推断 DST
    is_dst = _ny_is_dst_local(y, mo, d, hh, minute, second)
    offset_hours = -4 if is_dst else -5
    dt_local = datetime(y, mo, d, hh, minute, second, tzinfo=timezone(timedelta(hours=offset_hours)))
    dt_utc = dt_local.astimezone(timezone.utc)
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), label

def _normalize_rules(s: str) -> str:
    if not s: return ""
    # 换行类标签先替换成换行，其他标签去掉
    s = re.sub(r"(?i)</?(br|p|div|li|ul|ol|h\d)\b[^>]*>", "\n", s)
    s = re.sub(r"(?i)<a\b[^>]*>(.*?)</a>", r"\1", s)
    s = re.sub(r"<[^>]+>", "", s)
    # 压缩多余空白
    lines = [ln.strip() for ln in s.splitlines()]
    s = "\n".join([ln for ln in lines if ln])
    return s

def _normalize_token_value(x) -> str:
    """规范化 token 值为字符串。"""
    if x is None:
        return ""
    s = str(x).strip()
    # 移除可能的引号
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()
    return s

def _extract_token_from_dict(token_dict: Dict[str, Any]) -> str:
    """从 token 字典中提取 token ID。"""
    if not isinstance(token_dict, dict):
        return ""
    for k in ("tokenId", "id", "value", "token_id"):
        if k in token_dict and token_dict[k]:
            result = _normalize_token_value(token_dict[k])
            if result:
                return result
    return ""

def _extract_yes_no_tokens(stub: Dict[str, Any]) -> tuple[str, str]:
    """
    从 market stub 中提取 yesToken 和 noToken。
    返回 (yes_token, no_token) 元组，如果不存在则对应位置为空字符串。
    """
    yes_token = ""
    no_token = ""
    
    # 1) 优先从 yesToken / noToken 字段直接提取
    yes_token_dict = stub.get("yesToken")
    no_token_dict = stub.get("noToken")
    
    if isinstance(yes_token_dict, dict):
        yes_token = _extract_token_from_dict(yes_token_dict)
    if isinstance(no_token_dict, dict):
        no_token = _extract_token_from_dict(no_token_dict)
    
    # 如果已经从 yesToken/noToken 提取成功，直接返回
    if yes_token or no_token:
        return (yes_token, no_token)
    
    # 2) 从 clobTokenIds 提取（通常是列表，第一个是 yes，第二个是 no）
    v = stub.get("clobTokenIds")
    if isinstance(v, list) and len(v) >= 1:
        # 提取第一个作为 yes token
        first_item = v[0]
        if isinstance(first_item, dict):
            yes_token = _extract_token_from_dict(first_item)
        else:
            yes_token = _normalize_token_value(first_item)
        
        # 如果有第二个，作为 no token
        if len(v) >= 2:
            second_item = v[1]
            if isinstance(second_item, dict):
                no_token = _extract_token_from_dict(second_item)
            else:
                no_token = _normalize_token_value(second_item)
    elif isinstance(v, str):
        # 可能是 JSON 字符串格式
        s = v.strip()
        if s.startswith('[') and s.endswith(']'):
            try:
                arr = json.loads(s)
                if isinstance(arr, list) and len(arr) >= 1:
                    first_item = arr[0]
                    if isinstance(first_item, dict):
                        yes_token = _extract_token_from_dict(first_item)
                    else:
                        yes_token = _normalize_token_value(first_item)
                    
                    if len(arr) >= 2:
                        second_item = arr[1]
                        if isinstance(second_item, dict):
                            no_token = _extract_token_from_dict(second_item)
                        else:
                            no_token = _normalize_token_value(second_item)
            except Exception:
                # 解析失败，尝试按逗号分割
                parts = s.strip('[]').split(',')
                if len(parts) >= 1:
                    yes_token = _normalize_token_value(parts[0])
                if len(parts) >= 2:
                    no_token = _normalize_token_value(parts[1])
    
    # 3) 从 tokens / outcomeTokens 提取（通常第一个是 yes，第二个是 no）
    for key in ("tokens", "outcomeTokens"):
        tv = stub.get(key)
        if isinstance(tv, list) and len(tv) >= 1:
            # 如果 yes_token 还没提取到，尝试从第一个提取
            if not yes_token:
                first_item = tv[0]
                if isinstance(first_item, dict):
                    yes_token = _extract_token_from_dict(first_item)
                else:
                    yes_token = _normalize_token_value(first_item)
            
            # 如果有第二个且 no_token 还没提取到，尝试提取
            if len(tv) >= 2 and not no_token:
                second_item = tv[1]
                if isinstance(second_item, dict):
                    no_token = _extract_token_from_dict(second_item)
                else:
                    no_token = _normalize_token_value(second_item)
            
            # 如果已经提取到两个 token，可以提前返回
            if yes_token and no_token:
                break
    
    return (yes_token, no_token)

def _extract_first_token_id(stub: Dict[str, Any]) -> str:
    """从 market stub 中提取第一个 token ID（支持多种数据格式，向后兼容）。"""
    yes_token, no_token = _extract_yes_no_tokens(stub)
    return yes_token if yes_token else no_token

def _cat_to_str(x) -> str:
    """将 category/group/topic/tags 等字段安全转成字符串（兼容 str/dict/list）。"""
    if x is None:
        return ""
    if isinstance(x, str):
        return x.strip()
    if isinstance(x, dict):
        return str(x.get("name") or x.get("label") or x.get("title") or "").strip()
    if isinstance(x, list):
        parts = [_cat_to_str(it) for it in x]
        parts = [p for p in parts if p]
        return ",".join(parts)
    return str(x).strip()

_MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_RULE_BY_DEADLINE_RE = re.compile(
    r"\bby\s+([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4})\s*,\s*(\d{1,2}):(\d{2})\s*(AM|PM)\s*(ET|EST|EDT)\b",
    re.IGNORECASE
)

# 常见规则文本："... at 12 PM ET on December 26, 2025"
_RULE_AT_ON_RE = re.compile(
    r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\s*(ET|EST|EDT)?\s+on\s+([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4})\b",
    re.IGNORECASE
)

# 另一种常见顺序："... on December 26, 2025 at 12 PM ET"
_RULE_ON_AT_RE = re.compile(
    r"\bon\s+([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4})\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\s*(ET|EST|EDT)?\b",
    re.IGNORECASE
)

def parse_rules_datetime_iso(rules: str) -> str:
    """
    从 rules 里解析"明确的美东时间点"，并转成 UTC ISO（Z）。
    支持两类常见写法：
    1) 'by December 31, 2025, 11:59 PM ET'
    2) 'at 12 PM ET on December 26, 2025' / 'on December 26, 2025 at 12 PM ET'
    解析失败返回 ""。
    """
    if not rules:
        return ""

    # 先做轻量规范化（rules 可能包含 HTML）
    txt = _normalize_rules(str(rules))

    # 1) by ... deadline
    m = _RULE_BY_DEADLINE_RE.search(txt)
    if m:
        mon_s, day_s, year_s, hh_s, mm_s, ap_s, tz_s = m.groups()
        mon = _MONTH_MAP.get(mon_s.lower().strip(), 0)
        if mon <= 0:
            return ""
        day = int(day_s); year = int(year_s)
        hh = int(hh_s); minute = int(mm_s)
        ap = ap_s.upper().strip()
        tz = (tz_s or "ET").upper().strip()

        # 12h -> 24h
        if ap == "PM" and hh != 12:
            hh += 12
        if ap == "AM" and hh == 12:
            hh = 0

        # 处理时区：EST=-5, EDT=-4, ET 尽量用 zoneinfo（失败就按月份粗略推断）
        offset_hours = -5
        if tz == "EDT":
            offset_hours = -4
        elif tz == "EST":
            offset_hours = -5
        else:  # ET
            if _ZONEINFO_CACHE is not None:
                try:
                    dt_local = datetime(year, mon, day, hh, minute, 0, tzinfo=_ZONEINFO_CACHE("America/New_York"))
                    dt_utc = dt_local.astimezone(timezone.utc)
                    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    pass
            offset_hours = -4 if 4 <= mon <= 10 else -5

        dt_local = datetime(year, mon, day, hh, minute, 0, tzinfo=timezone(timedelta(hours=offset_hours)))
        dt_utc = dt_local.astimezone(timezone.utc)
        return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 2) at ... on ... / on ... at ...
    m2 = _RULE_AT_ON_RE.search(txt)
    if m2:
        hh_s, mm_s, ap_s, tz_s, mon_s, day_s, year_s = m2.groups()
    else:
        m3 = _RULE_ON_AT_RE.search(txt)
        if not m3:
            return ""
        mon_s, day_s, year_s, hh_s, mm_s, ap_s, tz_s = m3.groups()

    mon = _MONTH_MAP.get(mon_s.lower().strip(), 0)
    if mon <= 0:
        return ""
    day = int(day_s); year = int(year_s)
    hh = int(hh_s)
    minute = int(mm_s) if mm_s is not None and str(mm_s).strip() != "" else 0
    ap = ap_s.upper().strip()
    tz = (tz_s or "ET").upper().strip()  # 很多 rules 省略 ET，这里默认 ET

    # 12h -> 24h
    if ap == "PM" and hh != 12:
        hh += 12
    if ap == "AM" and hh == 12:
        hh = 0

    offset_hours = -5
    if tz == "EDT":
        offset_hours = -4
    elif tz == "EST":
        offset_hours = -5
    else:  # ET
        if _ZONEINFO_CACHE is not None:
            try:
                dt_local = datetime(year, mon, day, hh, minute, 0, tzinfo=_ZONEINFO_CACHE("America/New_York"))
                dt_utc = dt_local.astimezone(timezone.utc)
                return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                pass
        offset_hours = -4 if 4 <= mon <= 10 else -5

    dt_local = datetime(year, mon, day, hh, minute, 0, tzinfo=timezone(timedelta(hours=offset_hours)))
    dt_utc = dt_local.astimezone(timezone.utc)
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

def resolve_end_date_and_debug(mid: str, mm: Dict[str, Any], retry: int) -> (str, str):
    """
    优先级（优化：如果 Gamma endDate 已存在且非占位符，跳过 CLOB 调用以提升性能）：
    1) CLOB end_date_iso（仅当 Gamma endDate 为空或为 midnight UTC 占位符时调用）
    2) rules 文本 'by ... ET'
    3) Gamma endDate（mm 里已有）
    4) 仍不行：9999 拉很大

    Debug：正常 ""；只要出现"没拿到 end_date_iso / 用了兜底"就写原因。
    """
    dbg = []

    # 先检查 Gamma endDate 是否可用（非空且非 midnight UTC 占位符）
    gamma_end = (mm.get("endDate") or "").strip()
    gamma_is_valid = False
    if gamma_end:
        # 检查是否为 midnight UTC 占位符（需要修正的格式）
        if not _GAMMA_MIDNIGHT_UTC_RE.match(gamma_end):
            # Gamma endDate 有效，直接使用（跳过 CLOB 调用以提升性能）
            gamma_is_valid = True
            mm["endDate"] = gamma_end
            return mm["endDate"], ""

    # --- 1) CLOB end_date_iso 优先（仅在 Gamma endDate 无效时调用） ---
    cid = str(mm.get("condition_id") or "").strip()
    clob_end = ""
    if cid.startswith("0x") and len(cid) == 66:
        try:
            d = robust_get(f"{CLOB}/markets/{cid}", params=None, retry=max(1, retry), timeout=10)
            m = d.get("market") if isinstance(d, dict) and isinstance(d.get("market"), dict) else d
            raw = m.get("end_date_iso", None) if isinstance(m, dict) else None
            clob_end = (raw or "").strip() if raw is not None else ""
            if clob_end:
                # CLOB 也可能给出 midnight UTC（看起来像"日期占位"），按美东当日 23:59:59 修正
                fixed, label = _normalize_midnight_utc_to_et_time(clob_end, mm.get("rules") or "")
                if fixed and fixed != clob_end:
                    mm["endDate"] = fixed
                    return mm["endDate"], f"normalized_clob_midnight_to_et_{label}: {clob_end} -> {fixed}"
                mm["endDate"] = clob_end
                return mm["endDate"], ""  # 成功就不打 Debug（你要"正常为空"）
            else:
                dbg.append("clob_end_date_iso_missing")
        except Exception as e:
            dbg.append(f"clob_fetch_fail:{type(e).__name__}")
    else:
        dbg.append(f"invalid_condition_id={cid}")

    # --- 2) rules 文本兜底（优先于 Gamma endDate） ---
    rules = mm.get("rules") or ""
    rules_iso = parse_rules_datetime_iso(rules)
    if rules_iso:
        mm["endDate"] = rules_iso
        dbg.append("used_rules_datetime")
        return mm["endDate"], "; ".join(dbg)

    dbg.append("rules_deadline_parse_fail")

    # --- 3) Gamma endDate（已有） ---
    gamma_end = (mm.get("endDate") or "").strip()
    if gamma_end:
        # Gamma 偶发 'YYYY-MM-DDT00:00:00Z'：按 rules 选择 noon 或 eod 修正（只在此分支使用）
        fixed, label = _normalize_midnight_utc_to_et_time(gamma_end, mm.get("rules") or "")
        if fixed and fixed != gamma_end:
            mm["endDate"] = fixed
            dbg.append(f"normalized_gamma_midnight_to_et_{label}: {gamma_end} -> {fixed}")
            return mm["endDate"], "; ".join(dbg)
        return gamma_end, "; ".join(dbg)

    dbg.append("gamma_endDate_empty")

    # --- 4) 仍不行：9999 拉很大 ---
    mm["endDate"] = "9999-12-31T23:59:59Z"
    dbg.append("fallback_endDate_9999")
    return mm["endDate"], "; ".join(dbg)

# **Function definition**
def run_node(node):
    """
    单次调用仅处理一页（一个 offset），立刻返回一组 Outputs。
    偏移量通过 node['_state']['next_offset'] 记忆，以便持续运行时从上次位置继续。
    极简模式：只抓取 question, rules, endDate, category 核心信息。
    """
    Array = []

    # 读取输入
    limit        = int(node['Inputs'][0]['Num'])
    offset_start = int(node['Inputs'][1]['Num'])
    _closed_input = node['Inputs'][2]
    _closed_raw = _closed_input.get('Boolean')
    if _closed_raw is None:
        _closed_raw = _closed_input.get('Num') or _closed_input.get('Context')
    closed       = bool(_closed_raw)
    retry        = int(node['Inputs'][3]['Num'])
    _sp_dict     = node['Inputs'][4]
    _raw_save_path = _sp_dict.get('Context') if isinstance(_sp_dict, dict) else None
    if not _raw_save_path:
        _raw_save_path = _sp_dict.get('Num') if isinstance(_sp_dict, dict) else None
    save_path = str(_raw_save_path).strip() if _raw_save_path else "./output"
    
    try:
        offset_end = int(node['Inputs'][5]['Num']) if node['Inputs'][5]['Num'] is not None else -1
    except Exception:
        offset_end = -1
    
    # 读取 category_filter
    _cat_filter_input = node['Inputs'][6]
    category_filter = str(_cat_filter_input.get('Context') or _cat_filter_input.get('Num') or 'All').strip()

    # 读取 event_id（可选）
    _event_input = node['Inputs'][7] if len(node.get('Inputs', [])) >= 8 else {}
    event_id = str(_event_input.get('Context') or _event_input.get('Num') or '').strip()

    ensure_dir(save_path)

    # —— 取本次要处理的 offset（带状态续跑）——
    state = node.setdefault('_state', {})
    off = int(state.get('next_offset', offset_start))
    bounded_mode = (offset_end is not None and offset_end > 0)
    if bounded_mode:
        if off < offset_start:
            off = offset_start
        if off > offset_end:
            off = offset_end

    debug_lines: List[str] = []
    debug_lines.append(f"config: limit={limit}, offset=[{off},{off}], offset_end={offset_end}, bounded_mode={bounded_mode}, closed={closed}, retry={retry}, category_filter={category_filter}, event_id={event_id}")
    debug_lines.append(f"save_path={save_path}")

    # 1) 抓取该页 /markets
    if bounded_mode and off >= offset_end:
        node['_state']['finished'] = True
        return Array
    stubs_all: List[Dict[str, Any]] = fetch_markets(limit=limit, offset=off, closed=closed, retry=retry, category_filter=category_filter, event_id=event_id, debug_lines=debug_lines)
    markets_fetched = len(stubs_all)
    debug_lines.append(f"markets_fetched={markets_fetched}")

    # 2) 提取核心字段（仅保留 question, rules, endDate, token）
    records: List[Dict[str, Any]] = []
    token_empty_count = 0
    skipped_count = 0
    skipped_reasons = {"no_id": 0, "no_question": 0, "no_rules": 0, "no_endDate": 0}
    
    # 预编译正则表达式（避免在循环中重复编译）
    # 注意：_normalize_rules 内部使用的正则已经在模块级别编译，这里主要是优化提取逻辑
    
    for stub in stubs_all:
        mid = stub.get("id")
        if not mid:
            skipped_reasons["no_id"] += 1
            continue
        
        # 从列表页提取基础信息（优化：延迟规范化 rules，只在需要时处理）
        question = stub.get("question") or stub.get("title") or ""
        rules_raw = stub.get("description") or stub.get("rules") or ""
        endDate = stub.get("endDate") or stub.get("end_time") or stub.get("endTime") or ""
        yes_token, no_token = _extract_yes_no_tokens(stub)
        
        # 放宽条件：只要求 question 和 endDate，rules 可以为空（兼容性）
        if not question:
            skipped_reasons["no_question"] += 1
            continue
        if not endDate:
            skipped_reasons["no_endDate"] += 1
            continue
        
        # 统计 token 为空的数量（用于调试）
        if not yes_token and not no_token:
            token_empty_count += 1
        
        # 创建记录（包含 yesToken 和 noToken 两个字段）
        # 优化：rules 只在需要解析时才规范化（延迟处理）
        rec = {
            "question": question,
            "rules": rules_raw,  # 先保存原始值，后续需要时再规范化
            "endDate": endDate,
            "yesToken": yes_token,
            "noToken": no_token,
            "event_id": _extract_event_id_from_market_stub(stub),
        }
        records.append(rec)
    
    debug_lines.append(f"records_extracted={len(records)}")
    debug_lines.append(f"skipped_reasons: {skipped_reasons}")
    if token_empty_count > 0:
        debug_lines.append(f"token_empty_count={token_empty_count} (markets without token)")
    
    # 如果 records 为空，添加更多调试信息
    if len(records) == 0 and len(stubs_all) > 0:
        debug_lines.append(f"WARNING: all {len(stubs_all)} markets were skipped!")
        # 检查第一个 stub 的字段
        if stubs_all:
            first_stub = stubs_all[0]
            sample_keys = list(first_stub.keys())[:10]
            debug_lines.append(f"sample_stub_keys: {sample_keys}")
            debug_lines.append(f"sample_stub_question: {first_stub.get('question', 'MISSING')}")
            debug_lines.append(f"sample_stub_description: {str(first_stub.get('description', 'MISSING'))[:100]}")
            debug_lines.append(f"sample_stub_endDate: {first_stub.get('endDate', 'MISSING')}")
    
    # 3) 解析 endDate（优化：完全跳过 CLOB 调用，仅做基本解析以最大化性能）
    # 优化策略：只在 endDate 是 midnight UTC 占位符时才规范化 rules 并解析
    for rec in records:
        endDate_raw = rec.get("endDate", "").strip()
        if not endDate_raw:
            rec["endDate"] = ""
            # 即使 endDate 为空，也规范化 rules（保持一致性）
            if rec.get("rules"):
                rec["rules"] = _normalize_rules(rec["rules"])
            continue
        
        # 如果是 midnight UTC 占位符，尝试从 rules 解析或修正为 ET 时间
        if _GAMMA_MIDNIGHT_UTC_RE.match(endDate_raw):
            # 优先从 rules 解析明确的时间点（只在需要时规范化 rules）
            rules_raw = rec.get("rules") or ""
            if rules_raw:
                # 只在需要解析时才规范化 rules（避免不必要的正则操作）
                rules_normalized = _normalize_rules(rules_raw)
                rules_iso = parse_rules_datetime_iso(rules_normalized)
                if rules_iso:
                    rec["endDate"] = rules_iso
                    rec["rules"] = rules_normalized  # 同时更新规范化后的 rules
                else:
                    # 修正 midnight UTC 为 ET 时间（默认 23:59:59 ET）
                    fixed, _ = _normalize_midnight_utc_to_et_time(endDate_raw, rules_normalized)
                    rec["endDate"] = fixed if fixed else endDate_raw
                    rec["rules"] = rules_normalized  # 同时更新规范化后的 rules
            else:
                # 没有 rules，直接修正为 ET 时间
                fixed, _ = _normalize_midnight_utc_to_et_time(endDate_raw, "")
                rec["endDate"] = fixed if fixed else endDate_raw
        else:
            # endDate 已有效，直接使用（跳过所有 CLOB 调用以提升性能）
            # 规范化 rules（保持输出一致性，但这是轻量操作）
            if rec.get("rules"):
                rec["rules"] = _normalize_rules(rec["rules"])
            rec["endDate"] = endDate_raw
    
    debug_lines.append(f"final_records={len(records)}")

    # 7) 落盘（每页一个文件）
    fname = autogen_filename()
    full_path = os.path.join(save_path, fname)
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    try:
        fsize = os.path.getsize(full_path)
        debug_lines.append(f"target_file={full_path}")
        debug_lines.append(f"file_size={fsize} bytes")
    except Exception:
        debug_lines.append(f"target_file={full_path}")

    # 8) 组装该页的两路输出并 push 到 Array（仅本页）
    Outputs[0]['Num'] = None
    Outputs[0]['Context'] = full_path
    Outputs[0]['Description'] = f"Saved {len(records)} rows"

    Outputs[1]['Num'] = None
    Outputs[1]['Context'] = "\n".join(debug_lines)
    Outputs[1]['Description'] = 'Debug info'

    Array.append(copy.deepcopy(Outputs))

    # 9) 下一轮 offset
    if bounded_mode:
        if off >= offset_end:
            next_off = offset_end + 1
            debug_lines.append("bounded_progress=reached_end")
            try:
                node['_state']['finished'] = True
            except Exception:
                pass
        else:
            step = max(1, limit)
            cand = off + step
            next_off = cand if cand <= offset_end else offset_end
            if next_off >= offset_end:
                debug_lines.append("bounded_progress=next_hits_end")
                try:
                    node['_state']['finished'] = True
                except Exception:
                    pass
    else:
        next_off = off + max(1, limit)
        if markets_fetched < limit:
            next_off = off
            debug_lines.append("unbounded_progress=tail_reached_pause")
            try:
                node['_state']['finished'] = True
            except Exception:
                pass
    node['_state']['next_offset'] = next_off

    return Array
# **Function definition**
