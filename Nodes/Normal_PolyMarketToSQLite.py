import os
import json
import time
import random
import requests
import sqlite3
import copy
from typing import Dict, Any, List

# 全局会话，带 UA + 连接池优化
SESS = requests.Session()
SESS.headers.update({"User-Agent": "pm-screen/1.0"})
# 连接池：提升复用，减少握手超时
adapter = requests.adapters.HTTPAdapter(
    pool_connections=10,
    pool_maxsize=10,
    max_retries=0  # 我们自己控制重试
)
SESS.mount("https://", adapter)
SESS.mount("http://", adapter)

OutPutNum = 1
InPutNum = 2  # sqlite_path, closed

Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs  = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}',  'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}',  'Link': 0, 'IsLabel': True} for i in range(InPutNum)]

NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction = '全市场数据抓取直接存入SQLite数据库'

# 设置入/出参属性
Inputs[0]['Kind'] = 'String_FilePath'
Inputs[0]['name'] = 'db_path'
Inputs[0]['Isnecessary'] = True
Inputs[0]['Context'] = './polymarket.db'

Inputs[1]['Kind'] = 'Boolean'
Inputs[1]['name'] = 'closed'
Inputs[1]['Isnecessary'] = True
Inputs[1]['Boolean'] = False

Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Status'

GAMMA = "https://gamma-api.polymarket.com"

# =====================
# 带重试的网络请求（核心容错）
# =====================

def _backoff_sleep(attempt: int):
    """指数退避 + 随机抖动"""
    time.sleep((2 ** attempt) * 0.3 + random.random() * 0.5)

def _robust_get(url: str, params: dict = None, retry: int = 3, timeout: int = 15) -> requests.Response:
    """带重试 + 退避的 GET 请求，返回 Response 对象；全部失败抛异常"""
    last_err = None
    for attempt in range(retry + 1):
        try:
            r = SESS.get(url, params=params, timeout=timeout)
            return r
        except Exception as e:
            last_err = e
            if attempt < retry:
                _backoff_sleep(attempt)
    raise last_err

# =====================
# Token 提取
# =====================

def _normalize_token_value(x) -> str:
    """规范化 token 值为字符串。"""
    if x is None:
        return ""
    s = str(x).strip()
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
    yes_token = ""
    no_token = ""
    yes_token_dict = stub.get("yesToken")
    no_token_dict = stub.get("noToken")
    
    if isinstance(yes_token_dict, dict): yes_token = _extract_token_from_dict(yes_token_dict)
    if isinstance(no_token_dict, dict): no_token = _extract_token_from_dict(no_token_dict)
    if yes_token or no_token: return (yes_token, no_token)
    
    v = stub.get("clobTokenIds")
    if isinstance(v, list) and len(v) >= 1:
        yes_token = _extract_token_from_dict(v[0]) if isinstance(v[0], dict) else _normalize_token_value(v[0])
        if len(v) >= 2:
            no_token = _extract_token_from_dict(v[1]) if isinstance(v[1], dict) else _normalize_token_value(v[1])
    elif isinstance(v, str):
        s = v.strip()
        if s.startswith('[') and s.endswith(']'):
            try:
                arr = json.loads(s)
                if isinstance(arr, list) and len(arr) >= 1:
                    yes_token = _extract_token_from_dict(arr[0]) if isinstance(arr[0], dict) else _normalize_token_value(arr[0])
                    if len(arr) >= 2:
                        no_token = _extract_token_from_dict(arr[1]) if isinstance(arr[1], dict) else _normalize_token_value(arr[1])
            except Exception:
                parts = s.strip('[]').split(',')
                if len(parts) >= 1: yes_token = _normalize_token_value(parts[0])
                if len(parts) >= 2: no_token = _normalize_token_value(parts[1])
                
    for key in ("tokens", "outcomeTokens"):
        tv = stub.get(key)
        if isinstance(tv, list) and len(tv) >= 1:
            if not yes_token:
                yes_token = _extract_token_from_dict(tv[0]) if isinstance(tv[0], dict) else _normalize_token_value(tv[0])
            if len(tv) >= 2 and not no_token:
                no_token = _extract_token_from_dict(tv[1]) if isinstance(tv[1], dict) else _normalize_token_value(tv[1])
            if yes_token and no_token:
                break
    return (yes_token, no_token)

# =====================
# Tags 获取：/markets 列表不返回 tags，需通过 /events/{eid}/tags 或 /markets/{mid}/tags 补抓
# =====================

def _fetch_event_tags(event_id: str) -> List[Dict[str, Any]]:
    """通过 /events/{id}/tags 获取事件级别的 tags（带重试）"""
    try:
        r = _robust_get(f"{GAMMA}/events/{event_id}/tags", retry=2, timeout=12)
        if r.status_code != 200:
            return []
        data = r.json()
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return data["data"]
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []

def _fetch_market_tags(market_id: str) -> List[Dict[str, Any]]:
    """通过 /markets/{id}/tags 获取市场级别的 tags（兜底方案，带重试）"""
    try:
        r = _robust_get(f"{GAMMA}/markets/{market_id}/tags", retry=1, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return data["data"]
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []

ALLOWED_TAGS = {
    "crypto", "elections", "politics", "sports", "companies",
    "economic", "financial", "geopolitical", "tech", "world",
    "climate & science", "public health", "culture", "earnings",
    "regulations", "mentions"
}

def _is_allowed_tag(label: str, slug: str) -> bool:
    """判断 tag 是否在允许列表中"""
    lb = label.lower()
    sl = slug.lower()
    for a in ALLOWED_TAGS:
        if a == lb or a == sl:
            return True
        if a.replace(" & ", "-").replace(" ", "-") == sl:
            return True
    return False

def _tags_to_subject(tags: List[Dict[str, Any]]) -> str:
    """将 tags 列表过滤后转成 Subject 字符串（逗号分隔的 label，仅保留允许的 tags）"""
    if not tags:
        return ""
    labels = []
    for t in tags:
        if isinstance(t, dict):
            label = str(t.get("label") or t.get("name") or "").strip()
            slug = str(t.get("slug") or "").strip()
            if _is_allowed_tag(label, slug):
                labels.append(label if label else slug)
        elif isinstance(t, str) and t.strip():
            if t.strip().lower() in ALLOWED_TAGS:
                labels.append(t.strip())
    return ",".join(labels)

def _extract_event_id_from_stub(stub: Dict[str, Any]) -> str:
    """从 market stub 中提取 event_id"""
    for k in ("event_id", "eventId", "eventID", "EventID"):
        v = stub.get(k)
        if v:
            return str(v).strip()
    evs = stub.get("events")
    if isinstance(evs, list) and evs:
        first = evs[0]
        if isinstance(first, dict) and first.get("id"):
            return str(first["id"]).strip()
        if isinstance(first, str):
            return first.strip()
    return ""

def _batch_fetch_event_tags(event_ids: set, cache: dict):
    """批量预取本页所有新 event_id 的 tags（填入 cache），单个失败不影响整体"""
    new_eids = [eid for eid in event_ids if eid and eid not in cache]
    for eid in new_eids:
        cache[eid] = _fetch_event_tags(eid)
        # tags 请求之间加微小间隔，避免突发请求被限流
        time.sleep(0.05)

def run_node(node):
    db_path = node['Inputs'][0].get('Context') or node['Inputs'][0].get('Num') or 'polymarket.db'
    closed_val = node['Inputs'][1].get('Boolean')
    if closed_val is None:
        closed_val = bool(node['Inputs'][1].get('Context') or node['Inputs'][1].get('Num') or False)
    closed = closed_val
    
    # 建表语句
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS "polyMarket_Dictionary" (
        "ask" TEXT, "condition_id" TEXT, "question" TEXT, "Translation" TEXT, "now_ask_price" TEXT,
        "now_bid_price" TEXT, "Subject" TEXT, "endDate" TEXT, "rules" TEXT, "days_to_end" TEXT,
        "UseRss" TEXT, "url" TEXT, "option_name" TEXT, "condition_id_ext" TEXT, "token" TEXT,
        "bid" TEXT, "l1_spread_c" TEXT, "band_c_used" TEXT, "depth_ask_1c_usd" TEXT, "depth_bid_1c_usd" TEXT,
        "depth_1c_usd" TEXT, "depth_ask_1c_qty" TEXT, "depth_bid_1c_qty" TEXT, "vwap_ask_1c" TEXT,
        "vwap_bid_1c" TEXT, "n_orders_ask_1c" TEXT, "n_orders_bid_1c" TEXT, "top_concentration_ask_1c" TEXT,
        "top_concentration_bid_1c" TEXT, "roi_if_win" TEXT, "daily_eff_if_win" TEXT, "apr_eff_if_win" TEXT,
        "query_time_beijing" TEXT, "ingested_at" TEXT, "News" TEXT, "llm_is_clearcut" TEXT,
        "llm_prediction_p" TEXT, "llm_explain" TEXT, "suggested_qty" TEXT, "source_file" TEXT,
        "Score" TEXT, "resolutionSource" TEXT, "opp_ask_price" TEXT, "opp_bids_price" TEXT,
        "apr_eff_if_win_num" TEXT, "llm_is_Subject" TEXT, "llm_is_Matching" TEXT, "LLM_Think" TEXT,
        "Research_Debug" TEXT, "IsRightNow" TEXT, "KeyWords" TEXT, "LLM_researh" TEXT,
        "IsRuleInweb" TEXT, "opp_token" TEXT, "black" TEXT, "explain_suggest" TEXT,
        "yes_token" TEXT, "no_token" TEXT, "EventID" TEXT
    );
    """
    
    cols = [
        "ask", "condition_id", "question", "Translation", "now_ask_price", 
        "now_bid_price", "Subject", "endDate", "rules", "days_to_end", 
        "UseRss", "url", "option_name", "condition_id_ext", "token", 
        "bid", "l1_spread_c", "band_c_used", "depth_ask_1c_usd", "depth_bid_1c_usd", 
        "depth_1c_usd", "depth_ask_1c_qty", "depth_bid_1c_qty", "vwap_ask_1c", 
        "vwap_bid_1c", "n_orders_ask_1c", "n_orders_bid_1c", "top_concentration_ask_1c", 
        "top_concentration_bid_1c", "roi_if_win", "daily_eff_if_win", "apr_eff_if_win", 
        "query_time_beijing", "ingested_at", "News", "llm_is_clearcut", 
        "llm_prediction_p", "llm_explain", "suggested_qty", "source_file", 
        "Score", "resolutionSource", "opp_ask_price", "opp_bids_price", 
        "apr_eff_if_win_num", "llm_is_Subject", "llm_is_Matching", "LLM_Think", 
        "Research_Debug", "IsRightNow", "KeyWords", "LLM_researh", 
        "IsRuleInweb", "opp_token", "black", "explain_suggest", 
        "yes_token", "no_token", "EventID"
    ]
    
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(create_table_sql)
        cur.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_cond_id ON "polyMarket_Dictionary" ("condition_id")')
        conn.commit()
        
        # 获取数据库中已有的 condition_id，用于去重
        cur.execute('SELECT condition_id FROM "polyMarket_Dictionary"')
        existing_ids = set(row[0] for row in cur.fetchall() if row[0])
    except Exception as e:
        Outputs[0]['Context'] = f"数据库连接失败: {str(e)}"
        return [copy.deepcopy(Outputs)]
        
    limit = 100
    offset = 0
    total_inserted = 0
    event_tags_cache = {}   # event_id -> tags list，跨页缓存避免重复请求
    tags_hit = 0            # 成功获取 tags 的 market 数量
    tags_miss = 0           # 未获取到 tags 的 market 数量
    consecutive_errors = 0  # 连续错误计数
    MAX_CONSECUTIVE_ERRORS = 5  # 连续错误超过此数才真正放弃
    
    while True:
        # ====== 第一步：获取 /markets 列表（带重试） ======
        try:
            r = _robust_get(
                f"{GAMMA}/markets",
                params={"limit": limit, "offset": offset, "closed": str(closed).lower()},
                retry=3,
                timeout=20
            )
            if r.status_code != 200:
                # 非200：可能是限流(429)等，等一等再试
                consecutive_errors += 1
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    break
                time.sleep(3)
                continue
                
            data = r.json()
            if isinstance(data, dict) and "data" in data:
                markets = data["data"]
            elif isinstance(data, list):
                markets = data
            else:
                break
                
            if not markets or len(markets) == 0:
                break
            
            # 请求成功，重置连续错误计数
            consecutive_errors = 0
                
        except Exception as e:
            consecutive_errors += 1
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                # 连续失败太多次，保存已有数据后退出
                Outputs[0]['Context'] = (
                    f"连续{MAX_CONSECUTIVE_ERRORS}次请求失败，已安全退出。offset={offset}, 错误: {type(e).__name__}\n"
                    f"已插入: {total_inserted} 条\n"
                    f"Tags统计: 成功={tags_hit}, 失败={tags_miss}, event缓存={len(event_tags_cache)}个event"
                )
                try: conn.close()
                except: pass
                return [copy.deepcopy(Outputs)]
            # 还没到上限，等一会儿重试同一个 offset
            time.sleep(2 + consecutive_errors * 2)
            continue
        
        # ====== 第二步：先扫描本页所有 event_id，批量预取 tags ======
        page_stubs = []  # (stub, cond_id, eid, mid)
        page_event_ids = set()
        
        for stub in markets:
            cond_id = str(stub.get("conditionId") or stub.get("condition_id") or "")
            if not cond_id or cond_id in existing_ids:
                continue
            mid = str(stub.get("id") or "")
            eid = _extract_event_id_from_stub(stub)
            page_stubs.append((stub, cond_id, eid, mid))
            if eid:
                page_event_ids.add(eid)
        
        # 批量预取本页新 event_id 的 tags（单个失败不影响整体）
        _batch_fetch_event_tags(page_event_ids, event_tags_cache)
        
        # ====== 第三步：构建记录 ======
        records_to_insert = []
        for stub, cond_id, eid, mid in page_stubs:
            existing_ids.add(cond_id)
            
            rec = {k: "" for k in cols}
            rec["condition_id"] = cond_id
            
            # 从缓存取 tags（已在第二步批量预取）
            tags = event_tags_cache.get(eid, []) if eid else []
            
            # event tags 为空时，兜底用 /markets/{id}/tags（单个失败不影响）
            if not tags and mid:
                tags = _fetch_market_tags(mid)
            
            rec["Subject"] = _tags_to_subject(tags)
            if rec["Subject"]:
                tags_hit += 1
            else:
                tags_miss += 1
                
            rec["question"] = str(stub.get("question") or stub.get("title") or "")
            rec["rules"] = str(stub.get("description") or stub.get("rules") or "")
            rec["endDate"] = str(stub.get("endDate") or stub.get("end_time") or "")
            
            slug = stub.get("slug") or ""
            rec["url"] = f"https://polymarket.com/event/{slug}" if slug else ""
            
            rec["EventID"] = eid
                
            yes_token, no_token = _extract_yes_no_tokens(stub)
            rec["yes_token"] = yes_token
            rec["no_token"] = no_token
            rec["token"] = yes_token
            rec["option_name"] = "Yes"
            
            records_to_insert.append(tuple(rec[k] for k in cols))
        
        # ====== 第四步：写入数据库 ======
        if records_to_insert:
            try:
                placeholders = ",".join(["?"] * len(cols))
                insert_sql = f"INSERT OR IGNORE INTO \"polyMarket_Dictionary\" VALUES ({placeholders})"
                cur.executemany(insert_sql, records_to_insert)
                conn.commit()
                total_inserted += len(records_to_insert)
            except Exception as e:
                # 数据库写入失败，尝试回滚后继续
                try: conn.rollback()
                except: pass
        
        offset += limit
        
        # 限速：防止被 ban
        time.sleep(0.5)

    try:
        conn.close()
    except:
        pass
    
    Outputs[0]['Context'] = (
        f"抓取完成，共插入 {total_inserted} 条市场数据！\n"
        f"Tags统计: 成功={tags_hit}, 失败={tags_miss}, event缓存={len(event_tags_cache)}个event"
    )
    return [copy.deepcopy(Outputs)]
