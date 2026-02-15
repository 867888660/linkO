#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Polymarket 钱包指定 Token 仓位统计
- 输入：Token（clob tokenId，支持十进制/0x 十六进制）、Address（钱包地址 0x...）
- 输出：Quantity（仓位数量/份额）、AvgPrice（购买均价，加权）、Result（JSON 摘要）

实现风格对齐：Nodes/PolyMarket_WalletPositions_BatchSave.py
"""

import json
import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 可选：查询钱包在挂单（需要 py-clob-client + eth-account）
try:
    from eth_account import Account  # type: ignore
    from py_clob_client.client import ClobClient  # type: ignore
    _CLOB_IMPORTS_OK = True
except Exception:
    Account = None  # type: ignore
    ClobClient = None  # type: ignore
    _CLOB_IMPORTS_OK = False

# **节点输入输出定义**
OutPutNum = 5
InPutNum = 3
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
Inputs[0]['name'] = 'Token'
Inputs[0]['Kind'] = 'String'
Inputs[0]['Isnecessary'] = True
Inputs[0]['IsLabel'] = True
Inputs[0]['Context'] = ""

Inputs[1]['name'] = 'Address'
Inputs[1]['Kind'] = 'String_Key'
Inputs[1]['Isnecessary'] = True
Inputs[1]['IsLabel'] = True
Inputs[1]['Context'] = ""

# 新增：钱包私钥（用于查询在挂单；可直接填 0x... 或填环境变量名）
Inputs[2]['name'] = 'WALLET_PRIVATE_KEY'
Inputs[2]['Kind'] = 'String_Key'
Inputs[2]['Isnecessary'] = False
Inputs[2]['IsLabel'] = True
Inputs[2]['Context'] = ""

# Outputs 配置
Outputs[0]['name'] = 'Result'
Outputs[0]['Kind'] = 'String'
Outputs[1]['name'] = 'Quantity'
Outputs[1]['Kind'] = 'String'
Outputs[2]['name'] = 'AvgPrice'
Outputs[2]['Kind'] = 'String'
Outputs[3]['name'] = 'OpenOrdersCount'
Outputs[3]['Kind'] = 'String'
Outputs[4]['name'] = 'OpenOrdersQty'
Outputs[4]['Kind'] = 'String'

FunctionIntroduction = (
    '组件功能（简述代码整体功能）\n'
    '这是一个 Polymarket 钱包指定 Token 仓位统计节点：输入 token 与钱包地址，输出该 token 的仓位数量与购买均价。\n\n'
    '代码功能摘要（概括核心算法或主要处理步骤）\n'
    '节点调用 data-api /positions 拉取钱包全部仓位，按 tokenId 匹配目标 token（支持十进制/0x 十六进制），'
    '汇总 size（期权数量/份额），并用 avgPrice 做加权均价。若仓位带有 proxyWallet，会自动再查询 proxyWallet 并合并统计。\n\n'
    '参数\n```yaml\n'
    'inputs:\n'
    '  - name: Token\n    type: string\n    required: true\n    description: clob tokenId（十进制或 0x...）\n'
    '  - name: Address\n    type: string\n    required: true\n    description: 钱包地址（0x...）\n'
    '  - name: WALLET_PRIVATE_KEY\n    type: string\n    required: false\n    description: 钱包私钥（0x...）或环境变量名；用于查询该 token 的在挂单数量（open orders）\n'
    'outputs:\n'
    '  - name: Result\n    type: string\n    description: 返回结果 JSON 字符串（包含命中数量/均价/明细统计）\n'
    '  - name: Quantity\n    type: string\n    description: 该 token 的仓位数量（size 汇总）\n'
    '  - name: AvgPrice\n    type: string\n    description: 购买均价（avgPrice 按 size 加权；无数据则为空）\n'
    '  - name: OpenOrdersCount\n    type: string\n    description: 该 token 的钱包在挂单条数（status=live/partial_fill）。需要 py-clob-client/eth-account 且提供私钥。\n'
    '  - name: OpenOrdersQty\n    type: string\n    description: 该 token 的钱包在挂单总份数（尽量使用 remaining=size-filled；取不到则用 size 汇总）。\n'
    '```\n'
    '\n可选行为（环境变量开关）\n'
    '- PM_WTS_AUTO_CANCEL_UNFILLABLE=1（默认）：会自动撤掉当前无法立即成交的挂单（BUY: limit < best_ask；SELL: limit > best_bid）\n'
    '- PM_WTS_AUTO_CANCEL_UNFILLABLE=0：只统计不撤单\n'
)

# API 端点
DATA_API = "https://data-api.polymarket.com"

# ---- Network hardening: Session + Adapter(Retry) ----
RETRY_STATUS = {429, 500, 502, 503, 504}
RETRY_EXC = (
    requests.exceptions.SSLError,
    requests.exceptions.ConnectionError,
    requests.exceptions.ReadTimeout,
)


def build_session(max_retries: int = 2) -> requests.Session:
    """
    Build a requests.Session with connection pooling + urllib3 Retry.
    Note: we still do an outer retry loop with jittered exponential backoff for resilience.
    """
    retry = Retry(
        total=max_retries,
        connect=max_retries,
        read=max_retries,
        status=max_retries,
        backoff_factor=0.3,
        status_forcelist=sorted(RETRY_STATUS),
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    s = requests.Session()
    adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=retry)
    s.mount("https://", adapter)
    s.headers.update(
        {
            "User-Agent": "pm-wallet-token-stats/1.0",
            "Accept": "application/json",
            # EOF/TLS 中断场景下，关闭长连接往往更稳（代价是少量性能）
            "Connection": "close",
        }
    )
    return s


_HTTP_SESSION: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _HTTP_SESSION
    if _HTTP_SESSION is None:
        _HTTP_SESSION = build_session(max_retries=2)
    return _HTTP_SESSION


def _sleep_backoff(attempt: int, base: float = 1.5, cap: float = 12.0) -> float:
    t = min(base ** (attempt - 1), cap)
    return max(0.5, t)


def http_get_json(url: str, timeout: Tuple[float, float] = (5.0, 20.0), attempts: int = 6) -> Any:
    """
    Stable GET with:
    - requests.Session() connection pooling
    - urllib3 Retry for some transport/status issues
    - outer loop for retryable exceptions + 429/5xx with exp backoff + jitter
    """
    sess = _get_session()
    last_err: Optional[BaseException] = None

    for n in range(int(attempts)):
        try:
            r = sess.get(url, timeout=timeout)
            if int(getattr(r, "status_code", 0) or 0) in RETRY_STATUS:
                raise requests.exceptions.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r.json()
        except RETRY_EXC as e:
            last_err = e
        except requests.exceptions.HTTPError as e:
            last_err = e
        except Exception as e:
            last_err = e

        sleep_s = min(0.8 * (2 ** n) + random.uniform(0.0, 0.4), 15.0)
        try:
            print(
                f"[pm-wts][retry] attempt={n+1}/{attempts} "
                f"err={type(last_err).__name__} sleep={sleep_s:.2f}s url={url}"
            )
        except Exception:
            pass
        time.sleep(sleep_s)

    raise RuntimeError(f"http_get_json failed after {attempts} attempts: {last_err}")


def get_positions(user_addr: str, timeout: Tuple[float, float] = (5.0, 20.0), size_threshold: float = 0.0) -> List[Dict[str, Any]]:
    url = f"{DATA_API}/positions?user={user_addr}&sizeThreshold={size_threshold}"
    data = http_get_json(url, timeout=timeout)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return data["data"]
    # 不要悄悄返回空数组：避免“抓取失败/异常响应”被当作 0 仓位继续跑
    raise ValueError(f"unexpected positions response type: {type(data).__name__}")


def looks_like_evm_addr(s: Any) -> bool:
    if not isinstance(s, str):
        return False
    t = s.strip()
    return t.startswith("0x") and len(t) == 42


def pick_first(d: Dict[str, Any], keys: List[str]) -> Optional[Any]:
    for k in keys:
        if k in d and d[k] not in (None, "", "null"):
            return d[k]
    return None


def find_token_id(pos: Dict[str, Any]) -> Optional[str]:
    v = pick_first(pos, ["asset", "tokenId", "token_id", "clobTokenId", "clob_token_id", "id"])
    if v is None:
        return None
    return str(v).strip()


def collect_proxy_wallets(positions: List[Dict[str, Any]]) -> List[str]:
    found: List[str] = []
    seen = set()
    for p in positions:
        candidates: List[Any] = []
        candidates.append(p.get("proxyWallet"))
        candidates.append(p.get("proxy_wallet"))
        for k, v in p.items():
            if "proxy" in str(k).lower():
                candidates.append(v)
        for v in candidates:
            if looks_like_evm_addr(v):
                a = str(v).strip()
                if a.lower() not in seen:
                    seen.add(a.lower())
                    found.append(a)
    return found


def _resolve_env_or_value(s: Any) -> str:
    t = str(s or "").strip()
    if not t:
        return ""
    ev = os.getenv(t)
    return ev.strip() if isinstance(ev, str) and ev.strip() else t


def _to_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _token_to_int(token: str) -> Optional[int]:
    t = (token or "").strip()
    if not t:
        return None
    try:
        if t.startswith(("0x", "0X")):
            return int(t, 16)
        return int(t, 10)
    except Exception:
        return None


def _token_match(pos_token: str, target_token: str) -> bool:
    a = (pos_token or "").strip()
    b = (target_token or "").strip()
    if not a or not b:
        return False

    ai = _token_to_int(a)
    bi = _token_to_int(b)
    if ai is not None and bi is not None:
        return ai == bi

    # 兜底：字符串直接比较（忽略大小写）
    return a.lower() == b.lower()


def _env_first(keys: List[str]) -> str:
    """按优先级从环境变量读取第一个非空值。"""
    for k in keys:
        try:
            v = os.getenv(k)
        except Exception:
            v = None
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _bool_env(name: str, default: bool = True) -> bool:
    v = str(os.getenv(name, "") or "").strip().lower()
    if not v:
        return bool(default)
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    return bool(default)


def _fetch_best_levels_public(host: str, token_id: str, timeout: float = 10.0) -> Tuple[Optional[float], Optional[float], str]:
    """
    查询当前盘口 L1：
    - 优先 /book 拿 bids/asks
    - 若缺失 bid/ask，再用 /price(side=SELL/BUY) 兜底
    """
    base = str(host or "").strip().rstrip("/")
    tid = str(token_id or "").strip()
    if not base or not tid:
        return None, None, "invalid_input"

    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    src = "book"

    def _to_price(x: Any) -> Optional[float]:
        try:
            if isinstance(x, dict):
                v = x.get("price")
            elif isinstance(x, (list, tuple)) and len(x) >= 1:
                v = x[0]
            else:
                v = None
            return None if v is None else float(v)
        except Exception:
            return None

    # /book
    try:
        r = requests.get(f"{base}/book", params={"token_id": tid}, timeout=timeout, headers={"User-Agent": "pm-wallet-token-stats/1.0"})
        if r.status_code == 200:
            js = r.json() or {}
            bids = js.get("bids") or []
            asks = js.get("asks") or []
            bid_prices = [_to_price(x) for x in bids if _to_price(x) is not None]
            ask_prices = [_to_price(x) for x in asks if _to_price(x) is not None]
            best_bid = max(bid_prices) if bid_prices else None
            best_ask = min(ask_prices) if ask_prices else None
        else:
            src = f"book_http_{r.status_code}"
    except Exception as e:
        src = f"book_error:{type(e).__name__}"

    # /price fallback
    if best_bid is None:
        try:
            r = requests.get(f"{base}/price", params={"token_id": tid, "side": "SELL"}, timeout=timeout, headers={"User-Agent": "pm-wallet-token-stats/1.0"})
            if r.status_code == 200:
                js = r.json() or {}
                if js.get("price") is not None:
                    best_bid = float(js["price"])
                    src = src + "+price_bid"
        except Exception:
            pass
    if best_ask is None:
        try:
            r = requests.get(f"{base}/price", params={"token_id": tid, "side": "BUY"}, timeout=timeout, headers={"User-Agent": "pm-wallet-token-stats/1.0"})
            if r.status_code == 200:
                js = r.json() or {}
                if js.get("price") is not None:
                    best_ask = float(js["price"])
                    src = src + "+price_ask"
        except Exception:
            pass

    return best_bid, best_ask, src


def _count_open_orders_for_token(target_token: str, private_key: str = "", expected_addr: str = "") -> Tuple[int, float, float, str, Dict[str, Any]]:
    """
    查询该 token 的在挂单数量（best-effort）。
    说明：
    - Polymarket CLOB 的 open orders 通常需要鉴权；因此这里使用 py-clob-client + 私钥派生 API creds。
    - 不新增 Inputs（避免工作流错位），私钥从环境变量读取：
      POLYMARKET_PRIVATE_KEY / PM_PRIVATE_KEY / PRIVATE_KEY / WALLET_PRIVATE_KEY / PK
    - 若依赖缺失或未配置私钥，则返回 (0, reason)。
    """
    if not target_token:
        return 0, 0.0, 0.0, "empty_token", {}
    if not _CLOB_IMPORTS_OK:
        return 0, 0.0, 0.0, "missing_deps: pip install eth-account py-clob-client", {}

    pk_in = str(private_key or "").strip()
    pk = pk_in or _env_first(["POLYMARKET_PRIVATE_KEY", "PM_PRIVATE_KEY", "PRIVATE_KEY", "WALLET_PRIVATE_KEY", "PK"])
    if not pk:
        return 0, 0.0, 0.0, "missing_private_key_env", {}

    host = _env_first(["HOST", "POLYMARKET_HOST", "CLOB_HOST"]) or "https://clob.polymarket.com"
    try:
        chain_id = int(_env_first(["CHAIN_ID", "POLYMARKET_CHAIN_ID"]) or "137")
    except Exception:
        chain_id = 137

    # token 归一化为 int 再比较（兼容 0x / 十进制）
    tgt_int = _token_to_int(str(target_token).strip())

    try:
        # 由私钥推导钱包地址，并校验是否与输入 Address 一致（避免“查错钱包”导致计数异常）
        wallet_addr = ""
        try:
            wallet_addr = str(Account.from_key(pk).address).strip()  # type: ignore[union-attr]
        except Exception:
            wallet_addr = ""
        exp = str(expected_addr or "").strip()
        if exp and wallet_addr and exp.lower() != wallet_addr.lower():
            return 0, 0.0, 0.0, f"address_mismatch: input={exp} pk_wallet={wallet_addr}", {"wallet": wallet_addr}

        # 兼容不同版本 py-clob-client 的构造参数
        try:
            c = ClobClient(key=pk, host=host, chain_id=chain_id)  # type: ignore
        except TypeError:
            c = ClobClient(account=Account.from_key(pk), host=host, chain_id=chain_id)  # type: ignore

        # 尽力生成/设置 creds
        creds = None
        for m in ("create_or_derive_api_creds", "derive_api_key", "create_api_key"):
            if hasattr(c, m):
                try:
                    creds = getattr(c, m)()
                    break
                except Exception:
                    continue
        try:
            c.set_api_creds(creds)
        except Exception:
            pass

        # 可选：自动撤掉“当前无法立即成交”的挂单（默认开启，可用环境变量关闭）
        auto_cancel = _bool_env("PM_WTS_AUTO_CANCEL_UNFILLABLE", default=True)
        cancel_summary: Dict[str, Any] = {"enabled": auto_cancel}
        if auto_cancel:
            best_bid, best_ask, mkt_src = _fetch_best_levels_public(host, str(target_token), timeout=10.0)
            cancel_summary.update({"best_bid": best_bid, "best_ask": best_ask, "market_source": mkt_src})

        orders = []
        if hasattr(c, "get_orders"):
            orders = c.get_orders() or []
        if not isinstance(orders, list):
            return 0, 0.0, 0.0, "get_orders_not_list", {"wallet": wallet_addr, "cancel": cancel_summary}

        live_status = {"live", "partial_fill", "partial-fill", "partial"}
        n = 0
        qty_sum = 0.0
        rem_sum = 0.0
        samples: List[Dict[str, Any]] = []

        def _to_f(v: Any) -> Optional[float]:
            try:
                if v is None or v == "":
                    return None
                return float(v)
            except Exception:
                return None

        def _pick(d: Dict[str, Any], keys: List[str]) -> Any:
            for k in keys:
                if k in d and d[k] not in (None, "", "null"):
                    return d[k]
            return None

        # 撤单统计（如果启用）
        cancelled = 0
        cancelled_ids: List[str] = []
        kept_marketable = 0
        skipped_unknown = 0

        for od in orders:
            if not isinstance(od, dict):
                continue
            st = str(od.get("status") or "").strip().lower()
            # 兼容：LIVE / PARTIAL_FILL / PARTIALLY_FILLED / OPEN / ACTIVE
            if st not in live_status and (not st.startswith("partial")) and st not in ("open", "active"):
                continue
            # 注意：不要用 market 字段做 token 匹配（有些 SDK 会把 market/conditionId 放在 market 字段）
            tok = od.get("token_id") or od.get("tokenId") or od.get("asset_id")
            tok_s = str(tok).strip() if tok is not None else ""
            if not tok_s:
                continue
            if tgt_int is not None:
                oi = _token_to_int(tok_s)
                if oi is None or oi != tgt_int:
                    continue
            else:
                # 兜底：字符串比较
                if tok_s.lower() != str(target_token).strip().lower():
                    continue

            # 若启用 auto-cancel：先判断是否 marketable，不可成交则撤掉
            if auto_cancel:
                side = str(od.get("side") or "").strip().upper()
                # 兼容价格字段名
                limit_v = _pick(od, ["price", "limitPrice", "limit_price"])
                limit_f = _to_f(limit_v)
                is_marketable: Optional[bool] = None
                if side == "BUY" and limit_f is not None and cancel_summary.get("best_ask") is not None:
                    is_marketable = (float(limit_f) + 1e-12) >= float(cancel_summary["best_ask"])  # type: ignore[arg-type]
                elif side == "SELL" and limit_f is not None and cancel_summary.get("best_bid") is not None:
                    is_marketable = (float(limit_f) - 1e-12) <= float(cancel_summary["best_bid"])  # type: ignore[arg-type]
                else:
                    # 缺盘口/价格/side，保守跳过（不撤）
                    skipped_unknown += 1
                    is_marketable = None

                if is_marketable is True:
                    kept_marketable += 1
                elif is_marketable is False:
                    oid = od.get("id") or od.get("orderID") or od.get("order_id")
                    oid_s = str(oid or "").strip()
                    if oid_s:
                        # 兼容不同 SDK 的撤单方法
                        cancelled_one = False
                        for method in ("cancel_order", "cancel", "delete_order"):
                            if hasattr(c, method):
                                try:
                                    getattr(c, method)(oid_s)
                                    cancelled_one = True
                                    break
                                except Exception:
                                    continue
                        if cancelled_one:
                            cancelled += 1
                            if len(cancelled_ids) < 20:
                                cancelled_ids.append(oid_s)
                            # 撤掉的单不计入“当前在挂单”
                            continue
                    skipped_unknown += 1
                else:
                    # None：未知，保守不撤，继续计入挂单
                    pass

            n += 1

            # 统计挂单份数：优先 remaining=size-filled；取不到则用 size
            size_v = _pick(od, ["size", "quantity", "order_size", "original_size", "orig_size", "amount"])
            filled_v = _pick(od, ["filled", "filledSize", "filled_quantity", "filled_size", "filledQuantity"])
            remaining_v = _pick(od, ["remaining", "remaining_size", "remainingSize", "unfilled", "unfilled_size"])
            size_f = _to_f(size_v)
            filled_f = _to_f(filled_v)
            rem_f = _to_f(remaining_v)
            if rem_f is None and (size_f is not None):
                # filled 缺失则按 0 处理
                rem_f = max(0.0, size_f - (filled_f or 0.0))
            if size_f is not None:
                qty_sum += float(size_f)
            if rem_f is not None:
                rem_sum += float(rem_f)

            if len(samples) < 3:
                samples.append({
                    "order_id": od.get("id") or od.get("orderID") or od.get("order_id"),
                    "status": od.get("status"),
                    "side": od.get("side"),
                    "token_id": tok_s,
                    "price": od.get("price") or od.get("limitPrice") or od.get("limit_price"),
                    "size": size_v,
                    "filled": filled_v,
                    "remaining": remaining_v,
                    "expiration": od.get("expiration") or od.get("time_in_force") or od.get("tif"),
                })
        if auto_cancel:
            cancel_summary.update({
                "cancelled": cancelled,
                "kept_marketable": kept_marketable,
                "skipped_unknown": skipped_unknown,
                "cancelled_order_ids": cancelled_ids,
            })
        return int(n), float(qty_sum), float(rem_sum), "ok", {"wallet": wallet_addr, "samples": samples, "cancel": cancel_summary}
    except Exception as e:
        return 0, 0.0, 0.0, f"error:{type(e).__name__}", {}


def _aggregate_token_stats(positions: List[Dict[str, Any]], target_token: str) -> Tuple[float, Optional[float], int]:
    """
    返回：(total_qty, avg_price(weighted), matched_count)
    - total_qty: size 汇总（float）
    - avg_price: sum(|size|*avgPrice)/sum(|size|)；若没有可用 avgPrice 或 size 为 0，则返回 None
    """
    total_qty = 0.0
    sum_w = 0.0
    sum_wx = 0.0
    matched = 0

    for p in positions:
        tok = find_token_id(p)
        if not tok or not _token_match(tok, target_token):
            continue

        matched += 1
        size_val = pick_first(p, ["size", "shares", "quantity", "amount", "balance"])
        qty = _to_float(size_val) or 0.0
        total_qty += qty

        avg_val = pick_first(p, ["avgPrice", "avg_price", "averagePrice"])
        avg = _to_float(avg_val)
        w = abs(qty)
        if avg is not None and w > 0:
            sum_w += w
            sum_wx += avg * w

    avg_price = (sum_wx / sum_w) if sum_w > 0 else None
    return total_qty, avg_price, matched


def run_node(node) -> List[Dict[str, Any]]:
    def _get_input(idx: int) -> Any:
        try:
            return node['Inputs'][idx]['Context']
        except Exception:
            return None

    token_input = _resolve_env_or_value(_get_input(0))
    addr_input = _resolve_env_or_value(_get_input(1))
    pk_input = _resolve_env_or_value(_get_input(2))

    # 基本校验
    if not token_input:
        result = {"success": False, "error": "Token 输入为空"}
        Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False)
        # 失败时输出 -999，避免下游把 0 当成有效仓位/挂单
        Outputs[1]['Context'] = "-999"
        Outputs[2]['Context'] = ""
        Outputs[3]['Context'] = "-999"
        Outputs[4]['Context'] = "-999"
        return Outputs

    if not addr_input or not addr_input.startswith("0x") or len(addr_input) < 10:
        result = {"success": False, "error": "地址格式无效，请提供有效的 0x 地址", "addr": addr_input}
        Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False)
        Outputs[1]['Context'] = "-999"
        Outputs[2]['Context'] = ""
        Outputs[3]['Context'] = "-999"
        Outputs[4]['Context'] = "-999"
        return Outputs

    timeout: Tuple[float, float] = (5.0, 20.0)
    size_threshold = 0.0

    try:
        # 主钱包 positions
        positions = get_positions(addr_input, timeout=timeout, size_threshold=size_threshold)
        proxies = collect_proxy_wallets(positions)

        # 合并 proxy wallets（如果有）
        all_positions = list(positions)
        proxy_ok: List[str] = []
        proxy_fail: List[Dict[str, str]] = []
        for paddr in proxies:
            if paddr.lower() == addr_input.lower():
                continue
            try:
                ppos = get_positions(paddr, timeout=timeout, size_threshold=size_threshold)
                if ppos:
                    for x in ppos:
                        try:
                            x["_proxy_wallet"] = paddr
                        except Exception:
                            pass
                    all_positions.extend(ppos)
                proxy_ok.append(paddr)
            except Exception as e:
                proxy_fail.append({"addr": paddr, "error": str(e)})

        qty, avg_price, matched = _aggregate_token_stats(all_positions, token_input)

        open_orders_count, open_orders_qty, open_orders_remain, open_orders_reason, open_orders_debug = _count_open_orders_for_token(token_input, pk_input, addr_input)

        result = {
            "success": True,
            "addr": addr_input,
            "token": token_input,
            "matched_positions": matched,
            "quantity": qty,
            "avg_price": avg_price,
            "open_orders_count": open_orders_count,
            "open_orders_qty": open_orders_qty,
            "open_orders_remaining": open_orders_remain,
            "open_orders_reason": open_orders_reason,
            "open_orders_debug": open_orders_debug,
            "proxies": proxy_ok,
            "proxy_fail": proxy_fail,
            "positions_total": len(all_positions),
        }

        Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False)
        Outputs[1]['Context'] = str(qty)
        Outputs[2]['Context'] = ("" if avg_price is None else str(avg_price))
        Outputs[3]['Context'] = str(int(open_orders_count))
        # 优先输出 remaining（更符合“挂单量/未成交份数”口径）；若拿不到则退回 qty
        oo = open_orders_remain if (open_orders_remain is not None and open_orders_remain > 0) else open_orders_qty
        Outputs[4]['Context'] = str(oo)
        return Outputs

    except Exception as e:
        result = {"success": False, "error": str(e), "addr": addr_input, "token": token_input}
        Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False)
        Outputs[1]['Context'] = "-999"
        Outputs[2]['Context'] = ""
        Outputs[3]['Context'] = "-999"
        Outputs[4]['Context'] = "-999"
        return Outputs


