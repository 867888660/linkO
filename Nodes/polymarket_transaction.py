import json
import logging
import os
import time
import random
import traceback
import threading
import socket
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, List, Dict, Any
import re

# 标准库 HTTP（用于 Gamma API 查询；不引入额外第三方依赖）
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode, urlparse

# 可选：链上 redeem（需要 web3.py）。若缺失则在 BURN 模式给出友好提示。
try:
    from web3 import Web3  # type: ignore
except Exception:
    Web3 = None  # type: ignore

# 尝试导入第三方依赖；若缺失则标记并在运行时给出友好提示
try:
    from eth_account import Account  # type: ignore
    from py_clob_client.client import ClobClient  # type: ignore
    from py_clob_client.clob_types import OrderArgs  # type: ignore
    _IMPORTS_OK = True
except Exception:
    Account = None  # type: ignore
    ClobClient = None  # type: ignore
    OrderArgs = None  # type: ignore
    _IMPORTS_OK = False

# **节点输入输出定义**
OutPutNum = 6
InPutNum = 8
NodeKind = 'Normal'
# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs  = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}',  'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]
# **Initialize Outputs and Inputs arrays and assign names directly**
_input_names = [
    'Mode', 'PRICE', 'SIZE_SHARES', 'TIME_IN_FORCE_MODE',
    'PRIVATE_KEY', 'TOKEN_ID', 'HOST', 'CHAIN_ID'
]
for i, name in enumerate(_input_names):
    Inputs[i]['name'] = name
    Inputs[i]['Kind'] = 'String'
    Inputs[i]['Isnecessary'] = True

# **Assign properties to Inputs**
for output in Outputs:
    output['Kind'] = 'String'
Outputs[0]['name'] = 'Result'
Outputs[1]['name'] = 'DeBugging'  # DeBugging用于解锁调试功能，输出调试信息
Outputs[2]['name'] = 'Success'    # 单独输出布尔结果（字符串形式）
Outputs[3]['name'] = 'OrderID'    # 单独输出订单ID（若有）
Outputs[4]['name'] = 'tx_hash_hint'  # 相关链上交易哈希提示（单个时直接输出 0x...；多个时输出 JSON 列表；无则为空）
Outputs[5]['name'] = 'OpenOrdersCount'  # 当前 TOKEN_ID 的在挂单数量（status=live/partial_fill）
Inputs[0]['IsLabel'] = True
Inputs[0]['Context'] = 'BUY'#BUY|SELL|WITHDRAW_ORDER
Inputs[6]['IsLabel'] = True
Inputs[6]['Context'] = "https://clob.polymarket.com"
Inputs[7]['IsLabel'] = True
Inputs[7]['Context'] = "137"
Inputs[4]['IsLabel'] = True
Inputs[4]['Context'] = ""
Inputs[4]['Kind'] = 'String_Key'

# **功能说明**
FunctionIntroduction = (
    '组件功能（简述代码整体功能）\n'
    '这是一个基础的节点模板程序，用于在 Polymarket CLOB 上执行限价下单、撤单操作，并支持在市场已上报 payouts 后走链上 CTF redeemPositions 进行 redeem（burn winning token 换回抵押品）。节点读取 Mode、PRICE、SIZE_SHARES、TIME_IN_FORCE_MODE、'
    'PRIVATE_KEY、TOKEN_ID、HOST、CHAIN_ID 等输入，输出 Result（JSON 字符串）与 DeBugging（调试信息文本）。\n\n'
    '代码功能摘要（概括核心算法或主要处理步骤）\n'
    '程序定义了标准的节点结构，初始化输入输出节点数组并设置属性。核心处理逻辑在 run_node 函数中实现：根据 Mode 选择下单/撤单或 redeem 流程，完成 API 凭据生成、构建订单对象、发送订单/执行撤单，或通过 Gamma API 反查 market 并链上 redeemPositions，将结果与调试日志写入输出。\n\n'
    '参数\n```yaml\n'
    'inputs:\n'
    '  - name: Mode\n    type: string\n    required: true\n    description: 操作模式（BUY | SELL | WITHDRAW_ORDER | WITHDRAW_UNFILLABLE | BURN/REDEEM/DESTROY）\n'
    '  - name: PRICE\n    type: string\n    required: false\n    description: 限价，单位 USDC，步长 0.001\n'
    '  - name: SIZE_SHARES\n    type: string\n    required: false\n    description: 交易数量，单位 股\n'
    '  - name: TIME_IN_FORCE_MODE\n    type: string\n    required: false\n    description: 有效期模式，0=GTC,1=IOC,2=FOK\n'
    '  - name: PRIVATE_KEY\n    type: string\n    required: true\n    description: 钱包私钥（0x...）\n'
    '  - name: TOKEN_ID\n    type: string\n    required: true\n    description: 市场 outcome token id\n'
    '  - name: HOST\n    type: string\n    required: false\n    description: API 主机地址\n'
    '  - name: CHAIN_ID\n    type: string\n    required: false\n    description: 链 ID，默认 137\n'
    'outputs:\n'
    '  - name: Result\n    type: string\n    description: 返回结果 JSON 字符串\n'
    '  - name: DeBugging\n    type: string\n    description: 调试日志，多行文本\n'
    '  - name: Success\n    type: string\n    description: 本次操作是否成功（true/false 字符串）\n'
    '  - name: OrderID\n    type: string\n    description: 下单成功返回的订单ID（失败为空字符串）\n'
    '  - name: tx_hash_hint\n    type: string\n    description: 相关链上交易哈希“提示”。注意：下单成功不一定立刻有链上 tx_hash，可能为空；若只有 1 个哈希则直接输出 0x...；若有多个则输出 JSON 列表字符串。\n'
    '  - name: OpenOrdersCount\n    type: string\n    description: 当前 TOKEN_ID 的在挂单数量（live/partial_fill）。用于上层避免重复下单。\n'
    '```\n'
    '\n运行逻辑（用 - 列表描写详细流程）\n'
    '- 初始化输入输出节点数组，并设置节点属性（ID、名称、类型等）\n'
    '- 解析输入参数 Context，包括 Mode、PRICE、SIZE_SHARES 等\n'
    '- 构建 ClobClient 客户端，生成并设置 L2 API 凭据\n'
    '- 根据 Mode 执行不同流程：BUY/SELL 时创建并发送订单；WITHDRAW_ORDER 时列举并取消匹配挂单；WITHDRAW_UNFILLABLE 时先查询当前 L1 best bid/ask（/book，缺失再 /price 兜底），仅撤掉“当前无法立即成交”的挂单（BUY: limit < best_ask；SELL: limit > best_bid）；BURN/REDEEM/DESTROY 时先撤掉该 TOKEN_ID 挂单，再用 Gamma API 仅靠 TOKEN_ID 反查 conditionId 与 clobTokenIds(YES/NO)，最后链上调用 CTF redeemPositions，并用 balanceOf 前后差额 burned>0 作为“确实销毁成功”判定（BURN 需要环境变量 POLYGON_RPC/RPC_URL 以及 web3.py）\n'
    '- 收集结果数据和调试信息，赋值到输出节点 Context（含 Success、OrderID）\n'
    '- 返回包含 Result 和 DeBugging 的 Outputs 数组'
)


_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


def _is_hex_str(x: Any, n_bytes: Optional[int] = None, allow_0x: bool = True) -> bool:
    s = str(x or "").strip()
    if allow_0x and s.startswith("0x"):
        s = s[2:]
    if not s:
        return False
    if n_bytes is not None and len(s) != int(n_bytes) * 2:
        return False
    return _HEX_RE.fullmatch(s) is not None


def _normalize_private_key(pk: str) -> str:
    """把 PRIVATE_KEY 规范为 0x + 64 hex；并在非法时给出可读错误。"""
    s = str(pk or "").strip()
    # 去掉常见的复制粘贴污染：引号/空格
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()
    if s.startswith("0x"):
        h = s[2:].strip()
    else:
        h = s.strip()
    if not _is_hex_str(h, n_bytes=32, allow_0x=False):
        raise ValueError("PRIVATE_KEY 不是有效的十六进制私钥：需要 64 位 hex（可带 0x 前缀），且只能包含 0-9/a-f。")
    return "0x" + h.lower()


def _http_get_json_with_params(base_url: str, params: Dict[str, Any], timeout: float, debug: Optional[List[str]] = None) -> Any:
    qs = urlencode({k: v for k, v in (params or {}).items() if v is not None})
    url = f"{base_url}?{qs}" if qs else base_url
    return _http_get_json(url, timeout, debug)


def _fetch_best_levels_public(host: str, token_id: str, debug: List[str]) -> Dict[str, Optional[float]]:
    """
    查询当前盘口 L1：
    - 优先 GET {host}/book?token_id=...
    - 若缺失 bid/ask，则用 GET {host}/price?token_id=...&side=SELL/BUY 兜底
    返回：{"best_bid": float|None, "best_ask": float|None, "source": str}
    """
    base = str(host or "").strip().rstrip("/")
    tid = str(token_id or "").strip()
    out: Dict[str, Optional[float]] = {"best_bid": None, "best_ask": None, "source": None}  # type: ignore[assignment]
    if not base or not tid:
        out["source"] = "invalid_input"
        return out

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

    # 1) /book
    try:
        js = _http_get_json_with_params(f"{base}/book", {"token_id": tid}, REQUEST_TIMEOUT_SECONDS, debug)
        bids = js.get("bids") if isinstance(js, dict) else None
        asks = js.get("asks") if isinstance(js, dict) else None
        bid_prices = [_to_price(x) for x in (bids or []) if _to_price(x) is not None]
        ask_prices = [_to_price(x) for x in (asks or []) if _to_price(x) is not None]
        out["best_bid"] = max(bid_prices) if bid_prices else None
        out["best_ask"] = min(ask_prices) if ask_prices else None
        out["source"] = "book"
        _append_debug(debug, f"[mkt] /book tid={tid[:12]}… nbid={len(bids or [])} nask={len(asks or [])} bid={out['best_bid']} ask={out['best_ask']}")
    except Exception as e:
        out["source"] = f"book_error:{type(e).__name__}"
        _append_debug(debug, f"[mkt] /book failed: {e}")

    # 2) /price fallback
    if out.get("best_bid") is None:
        try:
            pj = _http_get_json_with_params(f"{base}/price", {"token_id": tid, "side": "SELL"}, REQUEST_TIMEOUT_SECONDS, debug)
            if isinstance(pj, dict) and pj.get("price") is not None:
                out["best_bid"] = float(pj["price"])
                out["source"] = (out.get("source") or "") + "+price_bid"
        except Exception as e:
            _append_debug(debug, f"[mkt] /price SELL failed (ignore): {e}")
    if out.get("best_ask") is None:
        try:
            pj = _http_get_json_with_params(f"{base}/price", {"token_id": tid, "side": "BUY"}, REQUEST_TIMEOUT_SECONDS, debug)
            if isinstance(pj, dict) and pj.get("price") is not None:
                out["best_ask"] = float(pj["price"])
                out["source"] = (out.get("source") or "") + "+price_ask"
        except Exception as e:
            _append_debug(debug, f"[mkt] /price BUY failed (ignore): {e}")

    return out


def _append_debug(debug_list: List[str], message: str) -> None:
    debug_list.append(message)
    try:
        logging.info(message)
        print(message)
    except Exception:
        pass


def _safe_truncate(v: Any, n: int = 400) -> str:
    s = str(v)
    return s if len(s) <= n else (s[:n] + "...(truncated)")


def _append_exception_debug(debug: List[str], label: str, exc: Exception) -> None:
    """输出更可定位的异常细节，便于分析并发下的 Request exception。"""
    _append_debug(debug, f"{label} 异常类型: {type(exc).__name__}")
    _append_debug(debug, f"{label} 异常repr: {repr(exc)}")
    _append_debug(debug, f"{label} 异常args: {_safe_truncate(getattr(exc, 'args', ())) }")

    # 常见 SDK 异常字段
    for attr in ("status_code", "error_message", "message", "code"):
        if hasattr(exc, attr):
            try:
                _append_debug(debug, f"{label} 异常字段 {attr}={_safe_truncate(getattr(exc, attr))}")
            except Exception:
                pass

    # 兼容 requests/httpx 风格 response 对象
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            _append_debug(debug, f"{label} response.status_code={getattr(resp, 'status_code', None)}")
            txt = getattr(resp, "text", None)
            if txt:
                _append_debug(debug, f"{label} response.text={_safe_truncate(txt, 800)}")
        except Exception:
            pass

    # 链式异常
    cause = getattr(exc, "__cause__", None)
    if cause is not None:
        _append_debug(debug, f"{label} cause: {type(cause).__name__} | {repr(cause)}")
    ctx = getattr(exc, "__context__", None)
    if ctx is not None and ctx is not cause:
        _append_debug(debug, f"{label} context: {type(ctx).__name__} | {repr(ctx)}")

    # 完整 traceback（单行压缩，避免日志太乱）
    try:
        tb = traceback.format_exc()
        if tb and tb.strip() and tb.strip() != "NoneType: None":
            _append_debug(debug, f"{label} traceback:\n{tb}")
    except Exception:
        pass


def _debug_host_diagnostics(host: str, debug: List[str]) -> None:
    """输出 host/DNS/代理 等诊断信息，快速判断是否是网络层问题。"""
    try:
        pu = urlparse(host)
        _append_debug(debug, f"[net] host={host}, scheme={pu.scheme}, netloc={pu.netloc}, path={pu.path or '/'}")
        target_host = pu.hostname
        target_port = pu.port or (443 if pu.scheme == "https" else 80)
        if target_host:
            try:
                infos = socket.getaddrinfo(target_host, target_port, proto=socket.IPPROTO_TCP)
                ip_list: List[str] = []
                for it in infos:
                    try:
                        ip = str(it[4][0])
                        if ip not in ip_list:
                            ip_list.append(ip)
                    except Exception:
                        continue
                _append_debug(debug, f"[net] dns {target_host}:{target_port} -> {ip_list[:6]}")
            except Exception as e:
                _append_debug(debug, f"[net] dns resolve failed: {type(e).__name__}: {e}")
    except Exception as e:
        _append_debug(debug, f"[net] host parse failed: {e}")

    # 常见代理环境变量
    proxy_keys = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy")
    proxy_info = {k: os.getenv(k) for k in proxy_keys if os.getenv(k)}
    if proxy_info:
        _append_debug(debug, f"[net] proxy env: {proxy_info}")
    else:
        _append_debug(debug, "[net] proxy env: <empty>")


def _extract_signed_raw_tx(signed: Any) -> Any:
    """
    兼容不同 eth-account/web3 版本的签名结果，尽力提取可用于 send_raw_transaction 的 raw tx bytes/HexBytes。
    - 常见字段：rawTransaction（旧） / raw_transaction（新）
    - 也可能是 dict / AttributeDict / namedtuple（支持 key 访问）
    """
    # 1) 属性形式
    raw_tx = getattr(signed, 'rawTransaction', None)
    if raw_tx is None:
        raw_tx = getattr(signed, 'raw_transaction', None)
    if raw_tx is not None:
        return raw_tx

    # 2) 映射/下标形式
    try:
        if isinstance(signed, dict):
            return signed.get('rawTransaction') or signed.get('raw_transaction')
        # AttributeDict / namedtuple / list/tuple
        if hasattr(signed, '__getitem__'):
            try:
                v = signed['rawTransaction']  # type: ignore[index]
                if v is not None:
                    return v
            except Exception:
                pass
            try:
                v = signed['raw_transaction']  # type: ignore[index]
                if v is not None:
                    return v
            except Exception:
                pass
    except Exception:
        pass

    raise RuntimeError(
        "签名结果缺少 rawTransaction/raw_transaction，可能是 eth-account/web3 版本不匹配。"
        "建议升级：pip install -U web3 eth-account"
    )


def _resolve_tif(mode: Optional[int]) -> str:
    if mode == 1:
        return 'IOC'
    if mode == 2:
        return 'FOK'
    return 'GTC'


# ============== 可配置超时与重试参数 ==============
REQUEST_TIMEOUT_SECONDS = int(os.getenv('POLYMARKET_TIMEOUT', '30'))  # 目标：提高默认超时时间
RETRY_MAX_ATTEMPTS = int(os.getenv('POLYMARKET_MAX_RETRIES', '8'))
RETRY_BACKOFF_BASE = float(os.getenv('POLYMARKET_BACKOFF_BASE', '1.5'))
RETRY_BACKOFF_CAP = float(os.getenv('POLYMARKET_BACKOFF_CAP', '20'))


def _sleep_backoff(attempt: int) -> float:
    delay = min((RETRY_BACKOFF_BASE ** (attempt - 1)), RETRY_BACKOFF_CAP)
    # 并发场景下加入轻微抖动，避免多个节点在同一时间点重试造成“惊群”
    jitter_ratio = float(os.getenv("POLYMARKET_BACKOFF_JITTER", "0.2") or 0.2)
    jitter_ratio = max(0.0, min(jitter_ratio, 1.0))
    if jitter_ratio > 0:
        low = max(0.1, 1.0 - jitter_ratio)
        high = 1.0 + jitter_ratio
        delay *= random.uniform(low, high)
    return max(0.5, delay)


def _with_retry(
    fn,
    *args,
    debug: Optional[List[str]] = None,
    label: str = '',
    retry_on_unsuccess: bool = False,
    max_attempts: Optional[int] = None,
    **kwargs
):
    last_exc = None
    attempts = int(max_attempts or RETRY_MAX_ATTEMPTS)
    attempts = max(1, attempts)
    for attempt in range(1, attempts + 1):
        try:
            res = fn(*args, **kwargs)
            # 若返回是 dict 且需要对 success 进行判断
            if retry_on_unsuccess and isinstance(res, dict):
                # 常见返回字段：success / status
                is_ok = bool(res.get('success') is True)
                if not is_ok:
                    raise RuntimeError(f"API unsuccessful response: {res}")
            return res
        except Exception as e:
            last_exc = e
            msg = str(e)
            if debug is not None:
                _append_debug(debug, f"{label} 第{attempt}次失败: {msg}")
                _append_exception_debug(debug, f"{label} 第{attempt}次失败细节", e)
            if attempt >= attempts:
                break
            sleep_s = _sleep_backoff(attempt)
            if debug is not None:
                _append_debug(debug, f"{label} {sleep_s:.1f}s 后重试...")
            time.sleep(sleep_s)
    raise last_exc if last_exc else RuntimeError(f"{label} 重试失败")


def _build_client(private_key: str, host: str, chain_id: int) -> Any:
    try:
        return ClobClient(key=private_key, host=host, chain_id=chain_id)  # type: ignore
    except TypeError:
        return ClobClient(account=Account.from_key(private_key), host=host, chain_id=chain_id)  # type: ignore


def _create_or_set_creds(c: Any, debug: List[str]) -> None:
    creds = None
    for m in ("create_or_derive_api_creds", "derive_api_key", "create_api_key"):
        if hasattr(c, m):
            try:
                creds = getattr(c, m)()
                _append_debug(debug, f"L2 creds OK via {m}")
                break
            except Exception as e:
                _append_debug(debug, f"L2 creds FAIL via {m} => {e}")
    
    c.set_api_creds(creds)


def _try_set_timeout(c: Any, seconds: int, debug: List[str]) -> None:
    # 尝试多种常见方式设置客户端超时（若库支持）
    tried = False
    for m in ("set_timeout", "set_request_timeout", "set_http_timeout"):
        if hasattr(c, m):
            tried = True
            try:
                getattr(c, m)(seconds)
                _append_debug(debug, f"timeout 设置成功 via {m}={seconds}s")
                return
            except Exception as e:
                _append_debug(debug, f"timeout 设置失败 via {m} => {e}")
    # 直接尝试设置属性
    for attr in ("timeout", "request_timeout", "http_timeout", "request_timeout_seconds"):
        if hasattr(c, attr):
            tried = True
            try:
                setattr(c, attr, seconds)
                _append_debug(debug, f"timeout 属性设置 {attr}={seconds}s")
                return
            except Exception as e:
                _append_debug(debug, f"timeout 属性设置失败 {attr} => {e}")
    if not tried:
        _append_debug(debug, "客户端不支持直接设置超时，将通过重试机制缓解超时问题")


def _validate_for_order(side: str, price: str, size_shares: float) -> None:
    if side not in ("BUY", "SELL"):
        raise ValueError(f"SIDE 必须是 BUY/SELL，收到: {side}")
    try:
        price_dec = Decimal(str(price))
    except (InvalidOperation, ValueError):
        raise ValueError(f"PRICE 不是有效数字，收到: {price}")
    # CLOB 价格是概率（USDC 计价），有效范围通常为 [0.001, 0.999]，步长 0.001
    # 远端会拒绝 price=1.0，并返回：min: 0.001 - max: 0.999
    if price_dec < Decimal("0.001") or price_dec > Decimal("0.999"):
        raise ValueError(f"PRICE 必须在 [0.001, 0.999] 之间，收到: {price}")
    # 校验：必须是 0.001 的整数倍
    scaled = price_dec * Decimal("1000")
    if scaled != scaled.to_integral_value():
        raise ValueError(f"PRICE 必须是 0.001 的整数倍，收到: {price}")
    if size_shares <= 0:
        raise ValueError("SIZE_SHARES 必须 > 0（份数/股数）")


def _list_open_orders(c: Any, debug: List[str]) -> List[Dict]:
    def _normalize(orders: List[Dict]) -> List[Dict]:
        out = []
        for od in (orders or []):
            st = od.get("status")
            oid = od.get("id") or od.get("orderID")
            tkn = od.get("token_id") or od.get("tokenId") or od.get("market") or od.get("asset_id")
            side = (od.get("side") or "").upper()
            price = od.get("price") or od.get("limitPrice") or od.get("limit_price")
            size = od.get("size") or od.get("quantity")
            filled = od.get("filled") or od.get("filledSize") or od.get("filled_quantity") or 0
            if oid:
                out.append({
                    "orderID": oid,
                    "status": st,
                    "token_id": str(tkn) if tkn is not None else "",
                    "side": side,
                    "price": float(price) if price is not None else None,
                    "size": float(size) if size is not None else None,
                    "filled": float(filled) if filled is not None else 0.0,
                    "_raw": od,
                })
        return out

    try:
        orders = _with_retry(c.get_orders, debug=debug, label="get_orders")
        out = _normalize(orders)
        _append_debug(debug, f"open orders fetched: {len(out)}")
        return out
    except Exception as e:
        _append_debug(debug, f"get_orders error: {e}")
        return []


def _count_open_orders_for_token(c: Any, token_id: str, debug: List[str]) -> int:
    """统计当前 token_id 的在挂单数量（status=live/partial_fill）。"""
    tok = str(token_id or "").strip()
    if not tok:
        return 0
    try:
        open_orders = _list_open_orders(c, debug)
        live = [
            od for od in (open_orders or [])
            if str(od.get("token_id") or "").strip() == tok
            and str(od.get("status") or "").strip().lower() in ("live", "partial_fill", "partial-fill", "partial")
        ]
        return int(len(live))
    except Exception as e:
        _append_debug(debug, f"count open orders failed (ignore): {e}")
        return 0


def _get_position_balance(c: Any, token_id: int, debug: List[str]) -> Optional[float]:
    """尽力获取某个 outcome token 的余额，若无法获取返回 None。"""
    # 方式1：get_positions -> 列表中查找
    for m in ("get_positions", "list_positions", "get_position_balances"):
        if hasattr(c, m):
            try:
                positions = getattr(c, m)()
                for p in positions or []:
                    try:
                        tid = int(p.get("token_id") or p.get("tokenId") or p.get("id"))
                    except Exception:
                        continue
                    if tid == token_id:
                        bal = p.get("balance") or p.get("amount") or p.get("quantity")
                        if bal is not None:
                            v = float(bal)
                            _append_debug(debug, f"position balance via {m}: token_id={token_id} -> {v}")
                            return v
            except Exception as e:
                _append_debug(debug, f"get positions via {m} failed => {e}")
    # 方式2：按 token_id 直接获取
    for m in ("get_position", "get_token_balance", "get_balance"):
        if hasattr(c, m):
            try:
                v = float(getattr(c, m)(token_id))
                _append_debug(debug, f"position balance via {m}: token_id={token_id} -> {v}")
                return v
            except Exception as e:
                _append_debug(debug, f"balance via {m} failed => {e}")
    _append_debug(debug, "无法查询到 position 余额，将跳过余额前置校验")
    return None


def _ensure_position_allowance(c: Any, token_id: int, required: float, debug: List[str]) -> None:
    """尽力确保 outcome token 的授权（允许撮合/结算合约转移）。"""
    attempts = [
        ("ensure_position_allowance", [(token_id, required), (token_id,)]),
        ("ensure_allowance", [(token_id, required), (token_id,)]),
        ("set_position_allowance", [(token_id, required), (token_id,)]),
        ("approve_token", [(token_id, int(2**128)), (token_id,)]),
        ("approve", [(token_id, int(2**128)), (token_id,)])
    ]
    for method, arg_variants in attempts:
        if hasattr(c, method):
            for args in arg_variants:
                try:
                    getattr(c, method)(*args)
                    _append_debug(debug, f"position allowance OK via {method}{args}")
                    return
                except TypeError:
                    # 形参不匹配则试下一个变体
                    continue
                except Exception as e:
                    _append_debug(debug, f"position allowance FAIL via {method}{args} => {e}")
    _append_debug(debug, "未能自动设置 position 授权，若持续 400: not enough balance/allowance，请手动在钱包或 SDK 中授权")


def _http_get_json(url: str, timeout: float, debug: Optional[List[str]] = None) -> Any:
    req = Request(url, headers={'User-Agent': 'polymarket-transaction-node'})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode('utf-8')
            return json.loads(data)
    except (HTTPError, URLError, TimeoutError, ValueError) as e:
        if debug is not None:
            _append_debug(debug, f"HTTP GET failed: {url} => {e}")
            _append_exception_debug(debug, f"HTTP GET failed detail [{url}]", e)
        raise


def _is_tx_hash_like(s: str) -> bool:
    v = str(s or "").strip()
    if not v:
        return False
    if v.startswith("0x") and len(v) == 66:
        return True
    # 允许不严格长度的 hash（某些接口可能返回不同格式），但至少需要 0x 前缀与一定长度
    return bool(v.startswith("0x") and len(v) >= 10)


def _extract_tx_hashes(obj: Any) -> List[str]:
    """从 trades/fills 的返回结构中尽力提取 tx hash 列表（去重）。"""
    out: List[str] = []

    def _add(v: Any) -> None:
        if v is None:
            return
        s = str(v).strip()
        if not _is_tx_hash_like(s):
            return
        if s not in out:
            out.append(s)

    # 常见返回形态：list[dict] 或 dict{data:[...]}
    # 另外：有些接口会直接在 dict 顶层给出 transactionsHashes/transactionHashes 列表（例如 post_order 响应）
    if isinstance(obj, dict):
        for k in ("transactionsHashes", "transactionHashes", "transaction_hashes", "tx_hashes"):
            v = obj.get(k)
            if isinstance(v, list):
                for it in v:
                    _add(it)
            elif isinstance(v, str):
                _add(v)

    records: Optional[List[Any]] = None
    if isinstance(obj, list):
        records = obj
    elif isinstance(obj, dict):
        for k in ("data", "results", "trades", "fills"):
            v = obj.get(k)
            if isinstance(v, list):
                records = v
                break
    if not isinstance(records, list):
        return out

    for r in records:
        if not isinstance(r, dict):
            continue
        for k in (
            "tx_hash", "txHash", "transaction_hash", "transactionHash",
            "hash", "txid", "txn_hash", "txnHash",
            "maker_tx_hash", "taker_tx_hash", "settlement_tx_hash",
        ):
            if k in r:
                _add(r.get(k))
        txo = r.get("transaction") or r.get("settlement")
        if isinstance(txo, dict):
            for k in ("hash", "tx_hash", "transactionHash", "transaction_hash"):
                if k in txo:
                    _add(txo.get(k))

    return out


def _clob_query_trades_fills_for_tx_hashes(
    host: str,
    token_id: str,
    order_id: str,
    debug: List[str],
    lookback_seconds: int = 3600,
) -> List[str]:
    """
    “尽力而为”的 tx_hash 探测：
    - 先查 {HOST}/trades，失败再查 {HOST}/fills（参照 passivityTrigger_PolyMarket.py 的做法）
    - 参数同时兼容 start_time / since
    - 下单成功不保证立刻有链上 tx；因此允许返回空列表
    """
    base = str(host or "").strip().rstrip("/")
    if not base:
        return []
    since = int(time.time()) - int(max(60, lookback_seconds))

    params_variants: List[Dict[str, Any]] = []
    if token_id:
        params_variants.append({"token_id": str(token_id), "start_time": since})
        params_variants.append({"token_id": str(token_id), "since": since})
    if order_id:
        params_variants.append({"order_id": str(order_id)})
        params_variants.append({"orderID": str(order_id)})
        if token_id:
            params_variants.append({"token_id": str(token_id), "order_id": str(order_id)})

    eps = ("/trades", "/fills")
    got: List[str] = []
    for p in params_variants:
        for ep in eps:
            url = f"{base}{ep}?{urlencode(p)}"
            try:
                _append_debug(debug, f"[txhint] GET {ep} params={p}")
                payload = _http_get_json(url, REQUEST_TIMEOUT_SECONDS, debug)
                hs = _extract_tx_hashes(payload)
                if hs:
                    _append_debug(debug, f"[txhint] {ep} matched tx_hashes: {hs[:5]}{' ...' if len(hs) > 5 else ''}")
                    for h in hs:
                        if h not in got:
                            got.append(h)
            except Exception as e:
                _append_debug(debug, f"[txhint] {ep} query failed: {e}")
    return got


def _tx_hash_hint_after_order(
    host: str,
    token_id: str,
    order_id: str,
    debug: List[str],
) -> List[str]:
    """
    下单后短轮询 trades/fills，尽力拿到最新相关 tx hash。
    注意：这是“提示”输出，不作为成功判定依据。
    """
    # 默认不对 /trades、/fills 做“匿名 HTTP 查询”，因为它们往往需要鉴权（否则 401/404）
    # 如需开启，设置：POLYMARKET_TXHINT_HTTP_ENABLE=1
    http_enable = str(os.getenv("POLYMARKET_TXHINT_HTTP_ENABLE", "0") or "0").strip() in ("1", "true", "yes", "on")
    if not http_enable:
        _append_debug(debug, "[txhint] 已跳过 /trades,/fills HTTP 查询（默认关闭，避免 401/404）。如需开启请设置 POLYMARKET_TXHINT_HTTP_ENABLE=1")
        return []

    attempts = int(os.getenv("POLYMARKET_TXHINT_ATTEMPTS", "3") or 3)
    attempts = max(1, min(attempts, 10))
    initial_wait = float(os.getenv("POLYMARKET_TXHINT_INITIAL_WAIT", "0.8") or 0.8)
    initial_wait = max(0.0, min(initial_wait, 10.0))
    if initial_wait > 0:
        time.sleep(initial_wait)

    got: List[str] = []
    for attempt in range(1, attempts + 1):
        hs = _clob_query_trades_fills_for_tx_hashes(host, token_id, order_id, debug)
        for h in hs:
            if h not in got:
                got.append(h)
        if got:
            return got
        if attempt < attempts:
            sleep_s = min(1.0 + 0.8 * attempt, 5.0)
            _append_debug(debug, f"[txhint] 暂未发现 tx_hash，{sleep_s:.1f}s 后再试 ({attempt}/{attempts})")
            time.sleep(sleep_s)
    return got


def _gamma_find_market_by_token_id(token_id: str, debug: List[str], limit: int = 200, max_pages: int = 200) -> Optional[Dict[str, Any]]:
    """仅靠 token_id 反查 Gamma market（不新增 Inputs）。
    Gamma /markets 是分页接口，字段 clobTokenIds 映射到一对 YES/NO token。"""
    base = os.getenv('GAMMA_HOST', 'https://gamma-api.polymarket.com')
    tok = str(token_id).strip()
    for page in range(max_pages):
        offset = page * limit
        url = f"{base}/markets?limit={limit}&offset={offset}"
        payload = _http_get_json(url, REQUEST_TIMEOUT_SECONDS, debug)
        markets = payload if isinstance(payload, list) else payload.get('data') if isinstance(payload, dict) else None
        if not markets:
            return None
        for m in markets:
            token_ids = m.get('clobTokenIds') or m.get('clobTokenIDs') or m.get('clob_token_ids')
            if isinstance(token_ids, str):
                try:
                    token_ids = json.loads(token_ids)
                except Exception:
                    token_ids = [t.strip() for t in token_ids.strip('[]').split(',') if t.strip()]
            if isinstance(token_ids, list) and any(str(x) == tok for x in token_ids):
                _append_debug(debug, f"Gamma matched market id={m.get('id')} question={m.get('question')}")
                return m
    return None


def _normalize_hex32(x: Any) -> str:
    s = str(x or '').strip()
    if not s:
        return ''
    if not s.startswith('0x'):
        s = '0x' + s
    if len(s) == 66:
        return s if _is_hex_str(s, n_bytes=32, allow_0x=True) else ''
    h = s[2:].strip()
    # 如果原始内容包含非 hex 字符，直接返回空（上层给出友好错误）
    if not _is_hex_str(h, allow_0x=False):
        return ''
    h = h.rjust(64, '0')[:64]
    return '0x' + h


def _burn_redeem_positions(private_key: str, token_id_int: int, market: Dict[str, Any], debug: List[str]) -> Dict[str, Any]:
    """链上 redeemPositions：把可兑换的 winning outcome token 烧掉换回 collateral。"""
    if Web3 is None:
        raise RuntimeError("BURN 模式需要 web3.py：pip install web3")

    rpc = os.getenv('POLYGON_RPC') or os.getenv('RPC_URL')
    if not rpc:
        # 默认 Polygon RPC（仍可用环境变量覆盖）。如需自定义默认值可设置 POLYGON_RPC_DEFAULT。
        rpc = os.getenv('POLYGON_RPC_DEFAULT', 'https://polygon-rpc.com')
        _append_debug(debug, f"未设置 POLYGON_RPC/RPC_URL，使用默认 RPC: {rpc}")
    if not rpc:
        raise RuntimeError("缺少 RPC。请设置环境变量 POLYGON_RPC 或 RPC_URL（Polygon/137）")

    # CTF 合约地址：官方文档给了两个 Polygon Mainnet 部署地址，优先用环境变量覆盖。
    ctf_addr = os.getenv('CTF_ADDRESS', '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045')

    # collateral 默认 USDC.e（Polygon PoS bridged USDC）。可用环境变量覆盖。
    collateral = os.getenv('COLLATERAL_TOKEN', '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174')

    condition_id = _normalize_hex32(market.get('conditionId') or market.get('condition_id'))
    if not condition_id:
        raw = market.get('conditionId') or market.get('condition_id')
        raise RuntimeError(f"Gamma market 的 conditionId 缺失或不是有效 hex（收到: {raw}），无法 redeem")
    if not _is_hex_str(condition_id, n_bytes=32, allow_0x=True):
        raise RuntimeError(f"Gamma market 的 conditionId 不是有效 hex32（收到: {condition_id}），无法 redeem")

    token_ids = market.get('clobTokenIds') or market.get('clobTokenIDs') or market.get('clob_token_ids')
    if isinstance(token_ids, str):
        try:
            token_ids = json.loads(token_ids)
        except Exception:
            token_ids = [t.strip() for t in token_ids.strip('[]').split(',') if t.strip()]
    if not (isinstance(token_ids, list) and len(token_ids) >= 2):
        raise RuntimeError("Gamma market 缺少 clobTokenIds（YES/NO），无法确定 indexSet")

    # 二元市场 indexSets 为 1 / 2（bitmask）
    idx = None
    for i, tid in enumerate(token_ids[:2]):
        if str(tid) == str(token_id_int):
            idx = i
            break
    if idx is None:
        raise RuntimeError("token_id 不在该 market 的 clobTokenIds 中，无法确定 indexSet")
    index_set = 1 if idx == 0 else 2

    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={'timeout': REQUEST_TIMEOUT_SECONDS}))
    # Polygon/Bor 等链的区块头 extraData 可能 >32 bytes，需要注入 POA middleware（兼容不同 web3 版本）
    injected = False
    inject_errs: List[str] = []
    # 1) 经典路径（web3.py v5/v6 常见）
    try:
        from web3.middleware import geth_poa_middleware  # type: ignore
        # 尝试多种注入方式
        try:
            w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        except (TypeError, AttributeError):
            # 某些版本可能需要实例化或使用 add()
            try:
                w3.middleware_onion.add(geth_poa_middleware)
            except Exception:
                w3.middleware_onion.inject(geth_poa_middleware(), layer=0)  # type: ignore
        injected = True
        _append_debug(debug, "已注入 geth_poa_middleware（解决 extraData 长度问题）")
    except Exception as e:
        inject_errs.append(f"geth_poa_middleware: {e}")
    # 2) 新路径（部分版本在 proof_of_authority 下）
    if not injected:
        try:
            from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware  # type: ignore
            try:
                w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            except TypeError:
                w3.middleware_onion.inject(ExtraDataToPOAMiddleware(), layer=0)  # type: ignore
            injected = True
            _append_debug(debug, "已注入 ExtraDataToPOAMiddleware（解决 extraData 长度问题）")
        except Exception as e:
            inject_errs.append(f"ExtraDataToPOAMiddleware: {e}")
    # 3) 进一步兜底：construct_poa_middleware()
    if not injected:
        try:
            from web3.middleware.proof_of_authority import construct_poa_middleware  # type: ignore
            w3.middleware_onion.inject(construct_poa_middleware(), layer=0)  # type: ignore
            injected = True
            _append_debug(debug, "已注入 construct_poa_middleware()（解决 extraData 长度问题）")
        except Exception as e:
            inject_errs.append(f"construct_poa_middleware: {e}")
    if not injected:
        raise RuntimeError(
            "连接 Polygon 需要 PoA middleware，但当前环境未能注入（请升级 web3 或更换 RPC）。注入错误："
            + " | ".join(inject_errs)
        )
    # 注入后立即测试：尝试获取最新区块，验证 middleware 是否生效
    try:
        _ = w3.eth.get_block('latest')
        _append_debug(debug, "PoA middleware 测试通过：成功获取最新区块")
    except Exception as test_e:
        err_msg = str(test_e)
        if 'extraData' in err_msg:
            raise RuntimeError(
                f"PoA middleware 注入失败或未生效（仍报 extraData 错误）。"
                f"请检查 web3 版本（建议 pip install -U web3）或更换 RPC。"
                f"测试错误：{err_msg}"
            )
        _append_debug(debug, f"PoA middleware 测试时出现其他错误（可忽略）：{test_e}")
    acct = w3.eth.account.from_key(private_key)
    wallet = acct.address

    abi = [
        {
            'inputs': [
                {'internalType': 'address', 'name': 'collateralToken', 'type': 'address'},
                {'internalType': 'bytes32', 'name': 'parentCollectionId', 'type': 'bytes32'},
                {'internalType': 'bytes32', 'name': 'conditionId', 'type': 'bytes32'},
                {'internalType': 'uint256[]', 'name': 'indexSets', 'type': 'uint256[]'},
            ],
            'name': 'redeemPositions',
            'outputs': [],
            'stateMutability': 'nonpayable',
            'type': 'function',
        },
        {
            'inputs': [
                {'internalType': 'address', 'name': 'account', 'type': 'address'},
                {'internalType': 'uint256', 'name': 'id', 'type': 'uint256'},
            ],
            'name': 'balanceOf',
            'outputs': [{'internalType': 'uint256', 'name': '', 'type': 'uint256'}],
            'stateMutability': 'view',
            'type': 'function',
        },
    ]

    ctf = w3.eth.contract(address=w3.to_checksum_address(ctf_addr), abi=abi)
    before_bal = int(ctf.functions.balanceOf(wallet, int(token_id_int)).call())
    _append_debug(debug, f"CTF balance(before) token_id={token_id_int} => {before_bal}")

    tx = ctf.functions.redeemPositions(
        w3.to_checksum_address(collateral),
        b'\x00' * 32,
        bytes.fromhex(condition_id[2:]),
        [int(index_set)],
    ).build_transaction({
        'from': wallet,
        'nonce': w3.eth.get_transaction_count(wallet),
        'chainId': int(os.getenv('CHAIN_ID', '137')),
    })
    try:
        tx['gas'] = w3.eth.estimate_gas(tx)
    except Exception as e:
        _append_debug(debug, f"estimate_gas failed: {e}")
    if 'gasPrice' not in tx and 'maxFeePerGas' not in tx:
        try:
            tx['gasPrice'] = w3.eth.gas_price
        except Exception:
            pass

    signed = acct.sign_transaction(tx)
    raw_tx = _extract_signed_raw_tx(signed)
    tx_hash = w3.eth.send_raw_transaction(raw_tx)
    _append_debug(debug, f"redeemPositions tx sent => {tx_hash.hex()}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=int(os.getenv('REDEEM_TIMEOUT', '180')))
    ok = int(getattr(receipt, 'status', 0)) == 1
    after_bal = int(ctf.functions.balanceOf(wallet, int(token_id_int)).call())
    _append_debug(debug, f"CTF balance(after) token_id={token_id_int} => {after_bal}")

    return {
        'tx_hash': tx_hash.hex(),
        'receipt_status': int(getattr(receipt, 'status', 0)),
        'burned': max(0, before_bal - after_bal),
        'index_set': index_set,
        'condition_id': condition_id,
        'collateral': collateral,
        'ctf': ctf_addr,
        'ok': ok,
    }


def run_node(node):
    Debugging: List[str] = []
    # 依赖缺失时，直接返回结构化错误，避免前端加载节点失败
    if not _IMPORTS_OK:
        Outputs[0]['Context'] = json.dumps({
            "success": False,
            "error": "缺少依赖库，请安装: eth-account, py-clob-client",
        }, ensure_ascii=False)
        Outputs[1]['Context'] = "\n".join([
            "依赖检查失败",
            "请在环境中安装: pip install eth-account py-clob-client",
        ])
        Outputs[2]['Context'] = "false"
        Outputs[3]['Context'] = ""
        Outputs[4]['Context'] = ""
        Outputs[5]['Context'] = ""
        return Outputs
    def _get_input(idx: int):
        try:
            return node['Inputs'][idx]['Context']
        except Exception:
            return None

    mode = str(_get_input(0) or "").strip().upper()
    price = _get_input(1)
    size = _get_input(2)
    tif_in = _get_input(3)
    private_key_input = str(_get_input(4) or "").strip()
    # 密钥使用原则：如果 private_key_input 是环境变量名且存在，使用环境变量的值；否则直接使用输入的字符串
    if private_key_input:
        env_value = os.getenv(private_key_input)
        if env_value:
            private_key = env_value  # 环境变量存在，使用环境变量的值
        else:
            private_key = private_key_input  # 环境变量不存在，直接使用输入的字符串
    else:
        private_key = ""
    token_id = str(_get_input(5) or "").strip()
    host = str(_get_input(6) or os.getenv("HOST", "https://clob.polymarket.com")).strip().rstrip("/")
    if host and not (host.startswith("http://") or host.startswith("https://")):
        host = "https://" + host
    chain_id = int(_get_input(7) or os.getenv("CHAIN_ID", 137))

    try:
        _append_debug(Debugging, f"[ctx] pid={os.getpid()} thread={threading.current_thread().name} mode={mode} chain_id={chain_id}")
        _debug_host_diagnostics(host, Debugging)
        if not private_key:
            raise ValueError("缺少 PRIVATE_KEY")
        if not token_id:
            raise ValueError("缺少 TOKEN_ID")

        # 更早、更清晰地校验 PRIVATE_KEY（否则会出现含糊的 Non-hexadecimal digit found）
        private_key = _normalize_private_key(private_key)

        tif_mode = int(float(tif_in)) if tif_in not in (None, "") else 0
        tif = _resolve_tif(tif_mode)

        client = _build_client(private_key, host, chain_id)
        _try_set_timeout(client, REQUEST_TIMEOUT_SECONDS, Debugging)
        # get_ok 在并发场景容易偶发 Request exception；改为“尽力检查，不作为致命失败”
        ok_retry_attempts = int(os.getenv("POLYMARKET_OK_MAX_RETRIES", "3") or 3)
        ok_retry_attempts = max(1, min(ok_retry_attempts, RETRY_MAX_ATTEMPTS))
        try:
            ok_val = _with_retry(client.get_ok, debug=Debugging, label="get_ok", max_attempts=ok_retry_attempts)
            _append_debug(Debugging, f"GET /ok (sdk) -> {ok_val}")
        except Exception as e:
            _append_debug(Debugging, f"get_ok(sdk) 失败（忽略并继续）: {e}")
            _append_exception_debug(Debugging, "get_ok(sdk) 失败细节", e)
            # 回退到公共 HTTP /ok，便于区分“SDK链路异常”与“主机不可达”
            try:
                ok_http = _http_get_json(f"{host}/ok", REQUEST_TIMEOUT_SECONDS, Debugging)
                _append_debug(Debugging, f"GET /ok (http) -> {ok_http}")
            except Exception as e2:
                _append_debug(Debugging, f"get_ok(http) 也失败（继续尝试后续 API）: {e2}")
                _append_exception_debug(Debugging, "get_ok(http) 失败细节", e2)
        # 凭据创建使用原始逻辑，避免不必要的改动与参数不匹配
        _create_or_set_creds(client, Debugging)
        try:
            _append_debug(Debugging, f"wallet: {Account.from_key(private_key).address}")
        except Exception as e:
            raise ValueError(
                f"PRIVATE_KEY 解析失败（常见原因：包含空格/引号/非 hex 字符，或长度不是 64 位 hex）。原始错误: {e}"
            )

        result: Dict[str, object] = {"success": False}
        order_id_out: str = ""
        success_out: bool = False
        tx_hash_hint: List[str] = []
        open_orders_count_out: int = 0

        if mode in ("BUY", "SELL"):
            if not price:
                raise ValueError("BUY/SELL 需要 PRICE")
            if not size:
                raise ValueError("BUY/SELL 需要 SIZE_SHARES")
            # 统一将价格规范到三位小数，并钳制到 [0.001, 0.999]，避免 0.9995 四舍五入到 1.000 被 CLOB 拒绝
            price_norm = Decimal(str(price)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
            if price_norm > Decimal("0.999"):
                _append_debug(Debugging, f"PRICE 过大（{price_norm}），已钳制到 0.999（CLOB max=0.999）")
                price_norm = Decimal("0.999")
            if price_norm < Decimal("0.001"):
                _append_debug(Debugging, f"PRICE 过小（{price_norm}），已钳制到 0.001（CLOB min=0.001）")
                price_norm = Decimal("0.001")
            _validate_for_order(mode, str(price_norm), float(size))
            _append_debug(Debugging, f"order args => side={mode}, price={price_norm}, size={size}, tif={tif}")
            # SELL 前置：检查余额并尝试确保授权
            token_id_int = int(token_id)
            if mode == "SELL":
                bal = _get_position_balance(client, token_id_int, Debugging)
                try:
                    need = float(size)
                except Exception:
                    need = None  # 安全兜底
                if bal is not None and need is not None and bal + 1e-9 < need:
                    _append_debug(Debugging, f"SELL 余额不足: 持有 {bal}, 需要 {need}。若为无持仓做空，请确保 USDC 余额与授权充足。")
                # 无论是否有持仓，尽力确保 position 授权
                _ensure_position_allowance(client, token_id_int, float(size), Debugging)
            # 将下单行为整体纳入重试：create_order + post_order
            def _place():
                oa = OrderArgs(token_id=int(token_id), side=mode, price=float(price_norm), size=float(size))
                order_obj_local = client.create_order(oa)
                return client.post_order(order_obj_local, tif)

            resp = _with_retry(_place, debug=Debugging, label="post_order", retry_on_unsuccess=True)
            _append_debug(Debugging, f"post_order -> {resp}")
            result.update({
                "success": True,
                "action": mode,
                "token_id": token_id,
                "tif": tif,
                "response": resp,
            })
            success_out = True
            try:
                order_id_out = str(resp.get("orderID") or "")
            except Exception:
                order_id_out = ""
            # tx_hash_hint：
            # 1) 优先从 post_order 响应里直接提取（matched 时经常自带 transactionsHashes）
            try:
                tx_hash_hint = _extract_tx_hashes(resp)
            except Exception:
                tx_hash_hint = []
            # 2) 若仍为空，再按需开启“外部查询”补齐（默认关闭，避免 401/404）
            if (not tx_hash_hint) and order_id_out:
                try:
                    tx_hash_hint = _tx_hash_hint_after_order(host, token_id, order_id_out, Debugging)
                except Exception as e:
                    _append_debug(Debugging, f"[txhint] lookup failed (ignore): {e}")

        elif mode == "WITHDRAW_ORDER":
            open_orders = [od for od in _list_open_orders(client, Debugging) if od['status'] in ("live", "partial_fill")]
            price_filter = round(float(Decimal(str(price)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)), 3) if price not in (None, "") else None
            targets = [
                od for od in open_orders
                if str(od['token_id']) == token_id
                and (
                    price_filter is None
                    or (od.get('price') is not None and round(float(od.get('price')), 3) == price_filter)
                )
            ]
            if not targets:
                _append_debug(Debugging, "未找到匹配条件的在挂单；如需按价格撤单请提供 PRICE。")
                result.update({"success": True, "action": "WITHDRAW_ORDER", "cancelled": 0, "matched": 0})
                success_out = True
            else:
                cancelled = 0
                for od in targets:
                    for method in ("cancel_order", "cancel", "delete_order"):
                        if hasattr(client, method):
                            r = _with_retry(getattr(client, method), od['orderID'], debug=Debugging, label=f"{method}({od['orderID']})")
                            cancelled += 1
                            _append_debug(Debugging, f"cancel -> {od['orderID']} :: {r}")
                            break
                result.update({"success": True, "action": "WITHDRAW_ORDER", "cancelled": cancelled, "matched": len(targets)})
                success_out = True
        elif mode == "WITHDRAW_UNFILLABLE":
            # 仅撤掉“当前无法立即成交”的挂单（不改变 Inputs，复用 PRICE 作为可选过滤）
            open_orders = [od for od in _list_open_orders(client, Debugging) if od.get('status') in ("live", "partial_fill")]
            price_filter = round(float(Decimal(str(price)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)), 3) if price not in (None, "") else None
            targets = [
                od for od in open_orders
                if str(od.get('token_id')) == token_id
                and (
                    price_filter is None
                    or (od.get('price') is not None and round(float(od.get('price')), 3) == price_filter)
                )
            ]
            if not targets:
                _append_debug(Debugging, "未找到匹配条件的在挂单（WITHDRAW_UNFILLABLE）；如需按价格过滤请提供 PRICE。")
                result.update({"success": True, "action": "WITHDRAW_UNFILLABLE", "cancelled": 0, "matched": 0, "skipped_unknown": 0})
                success_out = True
            else:
                mkt = _fetch_best_levels_public(host, token_id, Debugging)
                best_bid = mkt.get("best_bid")
                best_ask = mkt.get("best_ask")
                cancelled = 0
                skipped_unknown = 0
                kept_marketable = 0
                cancelled_ids: List[str] = []

                for od in targets:
                    side = str(od.get("side") or "").upper()
                    limit_p = od.get("price")
                    try:
                        limit_pf = float(limit_p) if limit_p is not None else None
                    except Exception:
                        limit_pf = None

                    # 无法判断盘口/价格时，保守：不撤
                    if limit_pf is None:
                        skipped_unknown += 1
                        continue

                    is_marketable: Optional[bool] = None
                    if side == "BUY":
                        if best_ask is not None:
                            is_marketable = (limit_pf + 1e-12) >= float(best_ask)
                    elif side == "SELL":
                        if best_bid is not None:
                            is_marketable = (limit_pf - 1e-12) <= float(best_bid)
                    else:
                        skipped_unknown += 1
                        continue

                    if is_marketable is None:
                        skipped_unknown += 1
                        continue
                    if is_marketable:
                        kept_marketable += 1
                        continue

                    oid = str(od.get("orderID") or "").strip()
                    if not oid:
                        skipped_unknown += 1
                        continue
                    # 触发撤单
                    for method in ("cancel_order", "cancel", "delete_order"):
                        if hasattr(client, method):
                            r = _with_retry(getattr(client, method), oid, debug=Debugging, label=f"{method}({oid})")
                            cancelled += 1
                            if len(cancelled_ids) < 20:
                                cancelled_ids.append(oid)
                            _append_debug(Debugging, f"cancel(unfillable) -> {oid} :: {r}")
                            break

                result.update({
                    "success": True,
                    "action": "WITHDRAW_UNFILLABLE",
                    "token_id": token_id,
                    "matched": len(targets),
                    "cancelled": cancelled,
                    "kept_marketable": kept_marketable,
                    "skipped_unknown": skipped_unknown,
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "market_source": mkt.get("source"),
                    "cancelled_order_ids": cancelled_ids,
                })
                success_out = True
        elif mode in ("BURN", "DESTROY", "REDEEM"):
            # 1) 先撤掉该 token 的所有在挂单（避免边 redeem 边成交导致余额变化）
            open_orders = [od for od in _list_open_orders(client, Debugging) if od.get('status') in ("live", "partial_fill")]
            targets = [od for od in open_orders if str(od.get('token_id')) == token_id]
            cancelled = 0
            for od in targets:
                oid = od.get('orderID') or od.get('order_id')
                if not oid:
                    continue
                for method in ("cancel_order", "cancel", "delete_order"):
                    if hasattr(client, method):
                        r = _with_retry(getattr(client, method), oid, debug=Debugging, label=f"{method}({oid})")
                        cancelled += 1
                        _append_debug(Debugging, f"cancel -> {oid} :: {r}")
                        break

            # 2) 反查 Gamma market（仅用 TOKEN_ID，不新增 Inputs）
            mkt = _gamma_find_market_by_token_id(token_id, Debugging)
            if not mkt:
                raise RuntimeError("未能通过 Gamma 找到对应 market（请检查 TOKEN_ID 是否正确，或增大扫描页数/limit）")

            # 3) 链上 redeemPositions（需要 web3.py + Polygon RPC）
            token_id_int = int(token_id)
            burn_info = _burn_redeem_positions(private_key, token_id_int, mkt, Debugging)

            # 4) 判定完成：tx 成功且 burned>0 视为“确实销毁/领取成功”
            burned = int(burn_info.get('burned') or 0)
            ok = bool(burn_info.get('ok'))
            success_out = bool(ok and burned > 0)
            result.update({
                "success": bool(ok),
                "action": "BURN",
                "token_id": token_id,
                "cancelled_orders": cancelled,
                "burn": burn_info,
                "note": ("redeem tx 成功但本次未烧掉任何 token：可能未到可领取阶段 / 不是赢方 / 余额为0" if ok and burned == 0 else ""),
            })
            # BURN 模式：tx_hash 是确定存在的（已发送链上交易），直接作为 hint 输出
            try:
                txh = str(burn_info.get("tx_hash") or "").strip()
                if txh:
                    tx_hash_hint = [txh]
            except Exception:
                tx_hash_hint = []
        else:
            raise ValueError("Mode 必须是 BUY、SELL、WITHDRAW_ORDER、WITHDRAW_UNFILLABLE 或 BURN")

        # 输出：当前 token 的在挂单数量（尽力查询；失败则为 0）
        open_orders_count_out = _count_open_orders_for_token(client, token_id, Debugging)

        # 同步到 Result（便于上层统一落库/追踪）；Outputs[4] 仍会单独输出一份
        try:
            result["tx_hash_hint"] = tx_hash_hint
        except Exception:
            pass
        try:
            result["open_orders_count"] = open_orders_count_out
        except Exception:
            pass

        Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False)
        Outputs[2]['Context'] = "true" if success_out else "false"
        Outputs[3]['Context'] = order_id_out
        # Output 展示：单个 => 0x..；多个 => JSON 列表；空 => ""
        if not tx_hash_hint:
            Outputs[4]['Context'] = ""
        elif len(tx_hash_hint) == 1:
            Outputs[4]['Context'] = str(tx_hash_hint[0])
        else:
            Outputs[4]['Context'] = json.dumps(tx_hash_hint, ensure_ascii=False)
        Outputs[5]['Context'] = str(int(open_orders_count_out))
    except Exception as e:
        err_msg = str(e)
        Outputs[0]['Context'] = json.dumps({"success": False, "error": err_msg}, ensure_ascii=False)
        _append_debug(Debugging, f"ERROR => {e}")
        _append_exception_debug(Debugging, "run_node 终止异常细节", e)
        low = err_msg.lower()
        if ("not enough balance" in low) or ("allowance" in low):
            _append_debug(Debugging, "诊断：余额或授权不足。")
            _append_debug(Debugging, "建议：")
            _append_debug(Debugging, "- SELL：确保钱包中持有足够的该 outcome token，或准备按空头方式卖出时钱包内有足够 USDC 抵押；")
            _append_debug(Debugging, "- 授权：给撮合/结算合约授权 outcome token/USDC（可在前端或通过 SDK 调用 set/ensure allowance）；")
            _append_debug(Debugging, "- 网络：确认当前链 ID 与主机配置正确（如 Polygon 主网 137 与 https://clob.polymarket.com）。")
        Outputs[2]['Context'] = "false"
        Outputs[3]['Context'] = ""
        Outputs[4]['Context'] = ""
        Outputs[5]['Context'] = ""

    Outputs[1]['Context'] = "\n".join(Debugging)
    return Outputs
