import json
import logging
import os
import time
from typing import Optional, List, Dict, Any
import requests

# 可选：链上 redeem（需要 web3.py）。若缺失则在运行时给出友好提示。
try:
    from web3 import Web3  # type: ignore
except Exception:
    Web3 = None  # type: ignore

# **节点输入输出定义**
OutPutNum = 4
InPutNum = 6
NodeKind = 'Normal'

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]

_input_names = [
    'PRIVATE_KEY',
    'CONDITION_ID',
    'TOKEN_ID',
    'OUTCOME',  # YES/NO
    'TX_HASH_HINT',  # optional: tx_hash_hint（优先从 receipt 解析参数）
    'API_KEY',       # optional: Alchemy API Key（未配置 POLYGON_RPC/RPC_URL 时拼接 RPC）
]
for i, name in enumerate(_input_names):
    Inputs[i]['name'] = name
    Inputs[i]['Kind'] = 'String'
    Inputs[i]['Isnecessary'] = True

# 私钥输入框类型
Inputs[0]['Kind'] = 'String_Key'
Inputs[0]['IsLabel'] = True
Inputs[0]['Context'] = ""

# condition_id 示例
Inputs[1]['IsLabel'] = True
Inputs[1]['Context'] = "0x" + "0" * 64

# token_id 示例（uint256）
Inputs[2]['IsLabel'] = True
Inputs[2]['Context'] = ""

# outcome 示例
Inputs[3]['IsLabel'] = True
Inputs[3]['Context'] = "YES"  # YES|NO|1|2

# tx_hash_hint 示例
Inputs[4]['IsLabel'] = True
Inputs[4]['Isnecessary'] = False
Inputs[4]['Context'] = ""

# api_key 示例
Inputs[5]['IsLabel'] = True
Inputs[5]['Isnecessary'] = False
Inputs[5]['Context'] = ""
Inputs[5]['Kind'] = 'String_Key'

# Outputs
for output in Outputs:
    output['Kind'] = 'String'
Outputs[0]['name'] = 'Result'
Outputs[1]['name'] = 'DeBugging'
Outputs[2]['name'] = 'Success'
Outputs[3]['name'] = 'TxHash'

FunctionIntroduction = (
    '组件功能（简述代码整体功能）\n'
    '这是一个精简的 redeem 节点，用于在 Polymarket 市场已上报 payouts 后，走链上 CTF 合约 redeemPositions 进行领取：'
    '会“烧掉可领取的 winning outcome token 并换回抵押品”。\n\n'
    '代码功能摘要（概括核心算法或主要处理步骤）\n'
    '节点 Inputs：PRIVATE_KEY、CONDITION_ID、TOKEN_ID、OUTCOME、TX_HASH_HINT、API_KEY。运行时读取 RPC/合约地址等环境变量，'
    '调用 CTF redeemPositions 后用 balanceOf 前后对比计算 burned，burned>0 视为确实销毁成功。\n\n'
    '参数\n```yaml\n'
    'inputs:\n'
    '  - name: PRIVATE_KEY\n    type: string\n    required: true\n    description: 钱包私钥（0x... 或环境变量名）\n'
    '  - name: CONDITION_ID\n    type: string\n    required: true\n    description: CTF conditionId（bytes32，0x... 64 hex）\n'
    '  - name: TOKEN_ID\n    type: string\n    required: true\n    description: CTF position token id（uint256，通常与 clobTokenIds 对应）\n'
    '  - name: OUTCOME\n    type: string\n    required: true\n    description: YES/NO（或 1/2，对应二元 indexSet bitmask）\n'
    '  - name: TX_HASH_HINT\n    type: string\n    required: false\n    description: 上游 transaction 节点输出的 tx_hash_hint；redeem 将优先从该 tx 的 receipt.logs 解析参数，失败再扫链\n'
    '  - name: API_KEY\n    type: string\n    required: false\n    description: Alchemy API Key（当未设置 POLYGON_RPC/RPC_URL 时，用它自动拼出 Polygon RPC）\n'
    'outputs:\n'
    '  - name: Result\n    type: string\n    description: 返回结果 JSON 字符串\n'
    '  - name: DeBugging\n    type: string\n    description: 调试日志，多行文本\n'
    '  - name: Success\n    type: string\n    description: 判定完成（tx 成功且 burned>0）时为 true，否则 false\n'
    '  - name: TxHash\n    type: string\n    description: 交易哈希（失败为空字符串）\n```\n'
    '\n环境变量（不新增 Inputs）\n'
    '- POLYGON_RPC 或 RPC_URL：Polygon(137) RPC（未设置则默认 https://polygon-rpc.com，可用 POLYGON_RPC_DEFAULT 覆盖默认）\n'
    '  - 推荐（解决公共 RPC 卡死/限制）：使用 Alchemy/QuickNode/Ankr/Infura 等付费/稳定 RPC\n'
    '  - PowerShell 示例：\n'
    '    $env:POLYGON_RPC="https://polygon-mainnet.g.alchemy.com/v2/<YOUR_KEY>"\n'
    '- CTF_ADDRESS：CTF 合约地址（默认 0x4D97...6045）\n'
    '- COLLATERAL_TOKEN：抵押品 token（默认 0x2791...4174，USDC.e）\n'
    '- CHAIN_ID：默认 137\n'
    '- REDEEM_TIMEOUT：等待回执超时秒数（默认 180）\n'
    '- TX 提示（优先走“快路”：直接从交易 receipt.logs 解析 parentCollectionId/collateral，解析不到才会扫链）：\n'
    '  - 支持的环境变量（任选其一）：CTF_PARAMS_TX_HASH / PARAMS_TX_HASH / POSITION_SPLIT_TX_HASH / TX_HASH_HINT\n'
    '  - PowerShell 示例：\n'
    '    $env:TX_HASH_HINT="<tx_hash_hint_from_transaction>"\n'
    '- 扫链参数（可选：让 eth_getLogs 更稳，减少 range too large/timeout）：\n'
    '  - CTF_EVENT_SCAN_STEP（默认 50000）\n'
    '  - CTF_EVENT_SCAN_MIN_STEP（默认 1）\n'
    '  - CTF_EVENT_SCAN_MAX_STEPS（默认 25）\n'
    '  - PowerShell 示例：\n'
    '    $env:CTF_EVENT_SCAN_STEP="2000"\n'
    '    $env:CTF_EVENT_SCAN_MIN_STEP="200"\n'
    '    $env:CTF_EVENT_SCAN_MAX_STEPS="200"\n'
)


def _append_debug(debug_list: List[str], message: str) -> None:
    debug_list.append(message)
    try:
        logging.info(message)
        print(message)
    except Exception:
        pass


def _normalize_hex32(x: Any) -> str:
    s = str(x or '').strip()
    if not s:
        return ''
    if not s.startswith('0x'):
        s = '0x' + s
    if len(s) == 66:
        return s
    h = s[2:]
    h = h.rjust(64, '0')[:64]
    return '0x' + h


def _resolve_index_set(outcome: str) -> int:
    s = str(outcome or '').strip().upper()
    if s in ('YES', 'Y', '1'):
        return 1
    if s in ('NO', 'N', '2'):
        return 2
    # 兜底：允许直接传数字
    try:
        v = int(float(s))
        if v in (1, 2):
            return v
    except Exception:
        pass
    raise ValueError("OUTCOME 必须是 YES/NO 或 1/2")


def _sleep_backoff(attempt: int, base: float, cap: float) -> float:
    delay = min((base ** (attempt - 1)), cap)
    return max(0.5, delay)


def _with_retry(fn, *args, debug: Optional[List[str]] = None, label: str = '', max_attempts: int = 5, backoff_base: float = 1.5, backoff_cap: float = 20.0, **kwargs):
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if debug is not None:
                _append_debug(debug, f"{label} 第{attempt}次失败: {e}")
            if attempt >= max_attempts:
                break
            sleep_s = _sleep_backoff(attempt, backoff_base, backoff_cap)
            if debug is not None:
                _append_debug(debug, f"{label} {sleep_s:.1f}s 后重试...")
            time.sleep(sleep_s)
    raise last_exc if last_exc else RuntimeError(f"{label} 重试失败")


def _extract_signed_raw_tx(signed: Any) -> Any:
    """
    兼容不同 eth-account/web3 版本的签名结果，尽力提取可用于 send_raw_transaction 的 raw tx bytes/HexBytes。
    - 常见字段：rawTransaction（旧） / raw_transaction（新）
    - 也可能是 dict / AttributeDict / namedtuple（支持 key 访问）
    """
    raw_tx = getattr(signed, 'rawTransaction', None)
    if raw_tx is None:
        raw_tx = getattr(signed, 'raw_transaction', None)
    if raw_tx is not None:
        return raw_tx

    try:
        if isinstance(signed, dict):
            v = signed.get('rawTransaction') or signed.get('raw_transaction')
            if v is not None:
                return v
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


def _gamma_fetch_market_meta_by_clob_token_id(clob_token_id: str, debug: List[str]) -> Optional[Dict[str, Any]]:
    """
    用 clob_token_id 反查 Gamma market 元数据。
    主要用途：拿到 collateralToken + parentCollectionId（某些市场 parentCollectionId != 0，会导致 positionId 计算不一致）
    """
    try:
        base = os.getenv("GAMMA_HOST", "https://gamma-api.polymarket.com").rstrip("/")

        def _as_markets(payload: Any) -> List[Dict[str, Any]]:
            if isinstance(payload, list):
                return [x for x in payload if isinstance(x, dict)]
            if isinstance(payload, dict):
                raw = payload.get("markets") or payload.get("data") or payload.get("results") or []
                if isinstance(raw, list):
                    return [x for x in raw if isinstance(x, dict)]
            return []

        def _get_json(url: str, params: Dict[str, Any]) -> Any:
            headers = {'User-Agent': 'polymarket-redeem-node'}
            last_err: Optional[Exception] = None
            for attempt in range(1, 4):
                try:
                    r = requests.get(url, params=params, timeout=20, headers=headers)
                    r.raise_for_status()
                    return r.json()
                except Exception as e:
                    last_err = e
                    _append_debug(debug, f"gamma http failed (attempt {attempt}/3): {e}")
                    time.sleep(min(2 * attempt, 5))
            raise last_err if last_err else RuntimeError("gamma http failed")

        # 1) 优先用官方过滤参数（最快）
        url = f"{base}/markets"
        data = _get_json(url, {"clob_token_ids": clob_token_id})
        markets = _as_markets(data)

        # 2) 兜底：分页扫描 markets（有时过滤参数不生效/被缓存/返回结构变化）
        if not markets:
            tok = str(clob_token_id).strip()
            limit = int(os.getenv("GAMMA_SCAN_LIMIT", "200") or 200)
            max_pages = int(os.getenv("GAMMA_SCAN_MAX_PAGES", "50") or 50)
            _append_debug(debug, f"gamma: direct query empty, fallback to scan markets (limit={limit}, pages<={max_pages})")
            for page in range(max_pages):
                offset = page * limit
                page_url = f"{base}/markets"
                payload = _get_json(page_url, {"limit": limit, "offset": offset})
                ms = _as_markets(payload)
                if not ms:
                    break
                for m0 in ms:
                    token_ids = m0.get("clobTokenIds") or m0.get("clobTokenIDs") or m0.get("clob_token_ids")
                    if isinstance(token_ids, str):
                        try:
                            token_ids = json.loads(token_ids)
                        except Exception:
                            token_ids = [t.strip() for t in token_ids.strip('[]').split(',') if t.strip()]
                    if isinstance(token_ids, list) and any(str(x) == tok for x in token_ids):
                        markets = [m0]
                        _append_debug(debug, f"gamma: scan matched market id={m0.get('id')} question={m0.get('question')}")
                        break
                if markets:
                    break

        if not markets:
            _append_debug(debug, f"gamma: 未找到 market (clob_token_ids={clob_token_id})")
            return None

        m = markets[0]

        collateral: Optional[str] = None
        for k in ["collateralToken", "collateral_token", "collateralTokenAddress", "collateralAddress"]:
            v = m.get(k)
            if isinstance(v, str) and v.startswith("0x") and len(v) == 42:
                collateral = v
                _append_debug(debug, f"gamma: collateral from {k} => {v}")
                break
        if collateral is None:
            for k, v in m.items():
                if "collateral" in str(k).lower() and isinstance(v, str) and v.startswith("0x") and len(v) == 42:
                    collateral = v
                    _append_debug(debug, f"gamma: collateral from {k} => {v}")
                    break

        parent_collection_id: Optional[str] = None
        for k in ["parentCollectionId", "parent_collection_id", "parentCollectionID"]:
            v = m.get(k)
            if isinstance(v, str) and v.startswith("0x") and len(v) == 66:
                parent_collection_id = v
                _append_debug(debug, f"gamma: parentCollectionId from {k} => {v}")
                break

        clob_token_ids = m.get("clobTokenIds") or m.get("clobTokenIDs") or m.get("clob_token_ids")
        if isinstance(clob_token_ids, str):
            try:
                clob_token_ids = json.loads(clob_token_ids)
            except Exception:
                pass
        if not isinstance(clob_token_ids, list):
            clob_token_ids = None

        return {
            "market": m,
            "collateral": collateral,
            "parentCollectionId": parent_collection_id,
            "clobTokenIds": clob_token_ids,
        }
    except Exception as e:
        _append_debug(debug, f"gamma fetch market meta failed: {e}")
        return None


def _gamma_find_market_by_condition_id(condition_id: str, debug: List[str]) -> Optional[Dict[str, Any]]:
    """
    当用 clob_token_id 反查失败时，兜底用 condition_id 扫描 Gamma /markets。
    说明：Gamma 未保证提供 condition_id 过滤参数，因此这里用分页扫描（可用环境变量调扫描范围）。
    """
    try:
        base = os.getenv("GAMMA_HOST", "https://gamma-api.polymarket.com").rstrip("/")
        cond = _normalize_hex32(condition_id)
        if not cond:
            return None
        limit = int(os.getenv("GAMMA_SCAN_LIMIT", "200") or 200)
        max_pages = int(os.getenv("GAMMA_SCAN_MAX_PAGES", "50") or 50)
        headers = {'User-Agent': 'polymarket-redeem-node'}
        _append_debug(debug, f"gamma: scan by condition_id (limit={limit}, pages<={max_pages})")
        for page in range(max_pages):
            offset = page * limit
            url = f"{base}/markets"
            r = requests.get(url, params={"limit": limit, "offset": offset}, timeout=20, headers=headers)
            r.raise_for_status()
            payload = r.json()
            markets = payload if isinstance(payload, list) else payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(markets, list) or not markets:
                break
            for m in markets:
                if not isinstance(m, dict):
                    continue
                cid = m.get("conditionId") or m.get("condition_id")
                if isinstance(cid, str) and _normalize_hex32(cid) == cond:
                    _append_debug(debug, f"gamma: conditionId matched market id={m.get('id')} question={m.get('question')}")
                    return m
        _append_debug(debug, f"gamma: scan by condition_id 未匹配到 market (condition_id={cond})")
        return None
    except Exception as e:
        _append_debug(debug, f"gamma scan by condition_id failed: {e}")
        return None


def _gamma_fetch_collateral_by_clob_token_id(clob_token_id: str, debug: List[str]) -> Optional[str]:
    meta = _gamma_fetch_market_meta_by_clob_token_id(clob_token_id, debug)
    v = (meta or {}).get("collateral")
    return v if isinstance(v, str) else None


def _topic_from_address(addr: str) -> str:
    """把 0x..address 转为 32 bytes topic（左补 0）"""
    a = str(addr or "").strip()
    if not (a.startswith("0x") and len(a) == 42):
        return ""
    return "0x" + ("0" * 24) + a[2:].lower()


def _to_hex32_topic(x: Any) -> str:
    """把 bytes/HexBytes/str 转为 0x + 64 hex"""
    if x is None:
        return ""
    # web3 的 topics 往往是 HexBytes
    try:
        if hasattr(x, "hex") and callable(getattr(x, "hex")):
            hx = x.hex()
            if hx.startswith("0x"):
                return _normalize_hex32(hx)
            return _normalize_hex32("0x" + hx)
    except Exception:
        pass
    return _normalize_hex32(x)


def _decode_positionsplit_data(w3: Any, data: Any, debug: List[str]) -> Optional[Dict[str, Any]]:
    """
    解码 ConditionalTokens/CTF 的 PositionSplit 事件 data（非 indexed 部分）：
      collateralToken(address), partition(uint256[]), amount(uint256)
    """
    try:
        codec = getattr(w3, "codec", None)
        if codec is None:
            return None
        types = ["address", "uint256[]", "uint256"]
        if hasattr(codec, "decode_abi"):
            collateral_token, partition, amount = codec.decode_abi(types, data)  # type: ignore[attr-defined]
        else:
            collateral_token, partition, amount = codec.decode(types, data)  # type: ignore[attr-defined]
        out = {
            "collateral": str(collateral_token),
            "partition": [int(x) for x in (partition or [])],
            "amount": int(amount),
        }
        return out
    except Exception as e:
        _append_debug(debug, f"decode PositionSplit data failed: {e}")
        return None


def _polygonscan_api_get(
    base_url: str,
    params: Dict[str, Any],
    debug: List[str],
    timeout: int = 60,
) -> Optional[Dict[str, Any]]:
    """轻量 polygonscan/etherscan 风格 API GET。失败返回 None，不抛异常。"""
    try:
        headers = {'User-Agent': 'polymarket-redeem-node'}
        # 允许通过环境变量调大超时，避免 Etherscan V2 偶发卡顿导致诊断失败
        try:
            # 默认已提高到 60s；若用户显式设置 env，则以 env 为准
            env_to = int(os.getenv("POLYGONSCAN_HTTP_TIMEOUT", "") or os.getenv("ETHERSCAN_HTTP_TIMEOUT", "") or 0)
            if env_to > 0:
                timeout = env_to
        except Exception:
            pass

        # 简单重试（避免网络抖动/对端偶发超时）
        max_attempts = int(os.getenv("POLYGONSCAN_HTTP_RETRY", "6") or 6)
        max_attempts = max(1, min(max_attempts, 8))
        backoff_base = float(os.getenv("POLYGONSCAN_HTTP_BACKOFF_BASE", "1.6") or 1.6)
        backoff_cap = float(os.getenv("POLYGONSCAN_HTTP_BACKOFF_CAP", "8.0") or 8.0)

        last_err: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                r = requests.get(str(base_url).strip(), params=params, timeout=timeout, headers=headers)
                if r.status_code != 200:
                    _append_debug(debug, f"polygonscan http {r.status_code}: {str(r.text)[:200]}")
                    return None
                data = r.json()
                if isinstance(data, dict):
                    return data
                _append_debug(debug, f"polygonscan bad json type: {type(data)}")
                return None
            except Exception as e:
                last_err = e
                _append_debug(debug, f"polygonscan request failed (attempt {attempt}/{max_attempts}): {e}")
                if attempt >= max_attempts:
                    break
                sleep_s = _sleep_backoff(attempt, backoff_base, backoff_cap)
                time.sleep(sleep_s)
        return None
    except Exception as e:
        _append_debug(debug, f"polygonscan request failed: {e}")
        return None


def _polygonscan_find_positionsplit_tx_hash(
    w3: Any,
    ctf_addr: str,
    condition_id_hex32: str,
    debug: List[str],
) -> Optional[str]:
    """
    当 RPC pruned / 禁用 eth_getLogs 时，用 Polygonscan 的 Logs API 反查该 condition 的 PositionSplit 交易哈希，
    再用现有 _try_params_from_tx_receipt() 从 tx receipt 解出 parentCollectionId / collateral / partition。
    不新增 Inputs：只读取环境变量 POLYGONSCAN_API_KEY（或 POLYSCAN_API_KEY）。
    """
    # 2025-08-15 起 Polygonscan/Etherscan 旧 V1 端点废弃，需迁移到 Etherscan API V2（base + chainid）
    # 为保持“只加一个环境变量”的体验：优先用 ETHERSCAN_API_KEY，其次复用 POLYGONSCAN_API_KEY/POLYSCAN_API_KEY
    api_key = (os.getenv("ETHERSCAN_API_KEY") or os.getenv("POLYGONSCAN_API_KEY") or os.getenv("POLYSCAN_API_KEY") or "").strip()
    if not api_key:
        return None

    base = (os.getenv("POLYGONSCAN_API_BASE") or os.getenv("ETHERSCAN_API_BASE") or "https://api.etherscan.io/v2/api").strip()
    # 如果用户还在用 polygonscan V1 base，则自动切到 etherscan v2 base
    if "polygonscan.com/api" in base.lower():
        base = "https://api.etherscan.io/v2/api"
    chainid = int(os.getenv("POLYGONSCAN_CHAIN_ID", "137") or 137)
    cond = _normalize_hex32(condition_id_hex32)
    if not cond:
        return None

    try:
        topic0 = w3.keccak(text="PositionSplit(address,address,bytes32,bytes32,uint256[],uint256)").hex()
    except Exception as e:
        _append_debug(debug, f"[polygonscan] build PositionSplit topic0 failed: {e}")
        return None

    def _parse_block_number(v: Any) -> int:
        s = str(v or "").strip()
        if not s:
            return 0
        try:
            if s.lower().startswith("0x"):
                return int(s, 16)
            return int(s, 10)
        except Exception:
            return 0

    params: Dict[str, Any] = {
        "chainid": int(chainid),
        "module": "logs",
        "action": "getLogs",
        "fromBlock": int(os.getenv("POLYGONSCAN_FROMBLOCK", "0") or 0),
        "toBlock": int(os.getenv("POLYGONSCAN_TOBLOCK", "9999999999") or 9999999999),
        "address": w3.to_checksum_address(ctf_addr),
        "topic0": topic0 if str(topic0).startswith("0x") else ("0x" + str(topic0)),
        "topic0_3_opr": "and",
        "topic3": cond,
        "page": 1,
        "offset": int(os.getenv("POLYGONSCAN_LOGS_OFFSET", "100") or 100),
        "apikey": api_key,
    }
    _append_debug(debug, f"[polygonscan] try Logs API (v2) getLogs(topic0=PositionSplit AND topic3=conditionId) chainid={chainid}")

    j = _polygonscan_api_get(base, params, debug)
    if not j:
        return None
    result = j.get("result")
    if not isinstance(result, list):
        # 常见：{"status":"0","message":"NOTOK","result":"Invalid API Key"} / rate limit 等
        if isinstance(result, str) and result.strip():
            _append_debug(debug, f"[polygonscan] logs api NOTOK: status={j.get('status')} message={j.get('message')} result={result[:200]}")
        else:
            _append_debug(debug, f"[polygonscan] logs api bad result type: {type(result)} status={j.get('status')} message={j.get('message')}")
        return None
    if not result:
        _append_debug(debug, f"[polygonscan] logs empty: status={j.get('status')} message={j.get('message')}")
        return None

    best_tx = ""
    best_bn = -1
    for it in result:
        if not isinstance(it, dict):
            continue
        txh = str(it.get("transactionHash") or it.get("transactionhash") or "").strip()
        if not txh.startswith("0x"):
            continue
        bn = _parse_block_number(it.get("blockNumber") or it.get("blocknumber"))
        if bn >= best_bn:
            best_bn = bn
            best_tx = txh

    if best_tx:
        _append_debug(debug, f"[polygonscan] logs hit => tx_hash={best_tx} block={best_bn}")
        return best_tx
    return None


def _polygonscan_find_tx_hash_by_token1155(
    wallet: str,
    ctf_addr: str,
    token_id_int: int,
    debug: List[str],
) -> Optional[str]:
    """兜底：用 account/token1155tx 拉 ERC1155 transfer，再按 tokenID 过滤找 tx hash。"""
    api_key = (os.getenv("ETHERSCAN_API_KEY") or os.getenv("POLYGONSCAN_API_KEY") or os.getenv("POLYSCAN_API_KEY") or "").strip()
    if not api_key:
        return None
    base = (os.getenv("POLYGONSCAN_API_BASE") or os.getenv("ETHERSCAN_API_BASE") or "https://api.etherscan.io/v2/api").strip()
    if "polygonscan.com/api" in base.lower():
        base = "https://api.etherscan.io/v2/api"
    chainid = int(os.getenv("POLYGONSCAN_CHAIN_ID", "137") or 137)

    max_pages = int(os.getenv("POLYGONSCAN_1155_MAX_PAGES", "20") or 20)
    offset = int(os.getenv("POLYGONSCAN_1155_OFFSET", "200") or 200)
    token_str = str(int(token_id_int))

    _append_debug(debug, f"[polygonscan] try token1155tx fallback (v2) (tokenID={token_str}, pages<={max_pages}, offset={offset}, chainid={chainid})")
    for page in range(1, max_pages + 1):
        params: Dict[str, Any] = {
            "chainid": int(chainid),
            "module": "account",
            "action": "token1155tx",
            "contractaddress": str(ctf_addr).strip(),
            "address": str(wallet).strip(),
            "page": int(page),
            "offset": int(offset),
            "sort": "desc",
            "apikey": api_key,
        }
        j = _polygonscan_api_get(base, params, debug)
        if not j:
            return None
        result = j.get("result")
        if not isinstance(result, list):
            if isinstance(result, str) and result.strip():
                _append_debug(debug, f"[polygonscan] token1155tx NOTOK: status={j.get('status')} message={j.get('message')} result={result[:200]}")
            else:
                _append_debug(debug, f"[polygonscan] token1155tx bad result type: {type(result)} status={j.get('status')} message={j.get('message')}")
            return None
        if not result:
            return None
        for it in result:
            if not isinstance(it, dict):
                continue
            tid = str(it.get("tokenID") or it.get("tokenId") or it.get("token_id") or "").strip()
            if tid == token_str:
                txh = str(it.get("hash") or it.get("transactionHash") or it.get("transactionhash") or "").strip()
                if txh.startswith("0x"):
                    _append_debug(debug, f"[polygonscan] token1155tx hit => tokenID={tid} tx_hash={txh}")
                    return txh
    return None


def _polygonscan_find_token1155_tx_hashes(
    wallet: str,
    ctf_addr: str,
    token_id_int: int,
    debug: List[str],
    max_hashes: int = 30,
) -> List[str]:
    """
    返回该 tokenID 的多笔关联交易哈希（按 token1155tx 扫描，优先新到旧）。
    说明：token1155tx 命中的第一笔 tx 很可能只是“转账”，receipt 不含 PositionSplit；
    因此诊断/反推参数时需要扫描多笔 tx，直到找到包含 PositionSplit 的那笔。
    """
    api_key = (os.getenv("ETHERSCAN_API_KEY") or os.getenv("POLYGONSCAN_API_KEY") or os.getenv("POLYSCAN_API_KEY") or "").strip()
    if not api_key:
        return []
    base = (os.getenv("POLYGONSCAN_API_BASE") or os.getenv("ETHERSCAN_API_BASE") or "https://api.etherscan.io/v2/api").strip()
    if "polygonscan.com/api" in base.lower():
        base = "https://api.etherscan.io/v2/api"
    chainid = int(os.getenv("POLYGONSCAN_CHAIN_ID", "137") or 137)

    max_pages = int(os.getenv("POLYGONSCAN_1155_MAX_PAGES", "20") or 20)
    offset = int(os.getenv("POLYGONSCAN_1155_OFFSET", "200") or 200)
    token_str = str(int(token_id_int))
    max_hashes = max(1, min(int(max_hashes), 200))

    out: List[str] = []
    seen = set()
    _append_debug(debug, f"[polygonscan] scan token1155tx hashes (tokenID={token_str}, pages<={max_pages}, offset={offset}, chainid={chainid}, max_hashes={max_hashes})")
    for page in range(1, max_pages + 1):
        params: Dict[str, Any] = {
            "chainid": int(chainid),
            "module": "account",
            "action": "token1155tx",
            "contractaddress": str(ctf_addr).strip(),
            "address": str(wallet).strip(),
            "page": int(page),
            "offset": int(offset),
            "sort": "desc",
            "apikey": api_key,
        }
        j = _polygonscan_api_get(base, params, debug)
        if not j:
            break
        result = j.get("result")
        if not isinstance(result, list) or not result:
            break
        for it in result:
            if not isinstance(it, dict):
                continue
            tid = str(it.get("tokenID") or it.get("tokenId") or it.get("token_id") or "").strip()
            if tid != token_str:
                continue
            txh = str(it.get("hash") or it.get("transactionHash") or it.get("transactionhash") or "").strip()
            if not txh.startswith("0x"):
                continue
            k = txh.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(txh)
            if len(out) >= max_hashes:
                return out
    return out


def _polygonscan_fetch_token1155_transfers_for_tokenid(
    address: str,
    ctf_addr: str,
    token_id_int: int,
    debug: List[str],
    max_pages: Optional[int] = None,
    offset: Optional[int] = None,
    max_items: int = 200,
) -> List[Dict[str, Any]]:
    """
    拉取某地址的 ERC1155 transfer 列表（token1155tx），并过滤出指定 tokenID 的转账条目。
    返回条目会尽量包含：hash/from/to/blockNumber/timeStamp。
    """
    api_key = (os.getenv("ETHERSCAN_API_KEY") or os.getenv("POLYGONSCAN_API_KEY") or os.getenv("POLYSCAN_API_KEY") or "").strip()
    if not api_key:
        return []
    base = (os.getenv("POLYGONSCAN_API_BASE") or os.getenv("ETHERSCAN_API_BASE") or "https://api.etherscan.io/v2/api").strip()
    if "polygonscan.com/api" in base.lower():
        base = "https://api.etherscan.io/v2/api"
    chainid = int(os.getenv("POLYGONSCAN_CHAIN_ID", "137") or 137)

    max_pages = int(max_pages if max_pages is not None else (os.getenv("POLYGONSCAN_1155_MAX_PAGES", "20") or 20))
    offset = int(offset if offset is not None else (os.getenv("POLYGONSCAN_1155_OFFSET", "200") or 200))
    token_str = str(int(token_id_int))
    max_items = max(1, min(int(max_items), 2000))

    out: List[Dict[str, Any]] = []
    seen = set()
    for page in range(1, max_pages + 1):
        params: Dict[str, Any] = {
            "chainid": int(chainid),
            "module": "account",
            "action": "token1155tx",
            "contractaddress": str(ctf_addr).strip(),
            "address": str(address).strip(),
            "page": int(page),
            "offset": int(offset),
            "sort": "desc",
            "apikey": api_key,
        }
        j = _polygonscan_api_get(base, params, debug)
        if not j:
            break
        result = j.get("result")
        if not isinstance(result, list) or not result:
            break
        for it in result:
            if not isinstance(it, dict):
                continue
            tid = str(it.get("tokenID") or it.get("tokenId") or it.get("token_id") or "").strip()
            if tid != token_str:
                continue
            txh = str(it.get("hash") or it.get("transactionHash") or it.get("transactionhash") or "").strip()
            if not txh.startswith("0x"):
                continue
            k = txh.lower() + "|" + tid
            if k in seen:
                continue
            seen.add(k)
            out.append({
                "hash": txh,
                "from": str(it.get("from") or it.get("fromAddress") or it.get("from_address") or "").strip(),
                "to": str(it.get("to") or it.get("toAddress") or it.get("to_address") or "").strip(),
                "blockNumber": str(it.get("blockNumber") or it.get("blocknumber") or ""),
                "timeStamp": str(it.get("timeStamp") or it.get("timestamp") or ""),
            })
            if len(out) >= max_items:
                return out
    return out


def _try_params_from_tx_receipt(
    w3: Any,
    tx_hash_hex: str,
    ctf_addr: str,
    condition_id: str,
    index_set: int,
    debug: List[str],
) -> Optional[Dict[str, Any]]:
    """
    不依赖 eth_getLogs：用户给一个交易哈希，直接从 receipt.logs 里找 PositionSplit 并解析出：
    - parentCollectionId（topic[2]）
    - collateralToken（data 里）
    适用场景：公共 RPC 禁止/限制 getLogs（你当前就是这种情况）。
    """
    try:
        txh = str(tx_hash_hex or "").strip()
        if not txh:
            return None
        if not txh.startswith("0x"):
            txh = "0x" + txh
        cond = _normalize_hex32(condition_id)
        if not cond:
            return None

        # keccak256("PositionSplit(address,address,bytes32,bytes32,uint256[],uint256)")
        topic0 = w3.keccak(text="PositionSplit(address,address,bytes32,bytes32,uint256[],uint256)").hex()
        if not topic0.startswith("0x"):
            topic0 = "0x" + topic0

        receipt = w3.eth.get_transaction_receipt(txh)
        logs = receipt.get("logs") if isinstance(receipt, dict) else getattr(receipt, "logs", None)
        if not logs:
            _append_debug(debug, f"[txhint] receipt has no logs: {txh}")
            return None

        for lg in logs:
            try:
                addr = lg.get("address") if isinstance(lg, dict) else getattr(lg, "address", "")
                if str(addr).lower() != str(ctf_addr).lower():
                    continue
                topics_l = lg.get("topics") if isinstance(lg, dict) else getattr(lg, "topics", None)
                data_l = lg.get("data") if isinstance(lg, dict) else getattr(lg, "data", None)
                if not topics_l or len(topics_l) < 4:
                    continue
                if _to_hex32_topic(topics_l[0]).lower() != _to_hex32_topic(topic0).lower():
                    continue
                cond_hex = _to_hex32_topic(topics_l[3])
                if cond_hex != cond:
                    continue
                parent_hex = _to_hex32_topic(topics_l[2])
                dec = _decode_positionsplit_data(w3, data_l, debug)
                if not dec:
                    continue
                part = dec.get("partition") or []
                if index_set and isinstance(part, list) and part and int(index_set) not in [int(x) for x in part]:
                    # 提示：如果你给的是“merge/transfer”的 tx，这里可能匹配不到
                    continue
                out = {
                    "parentCollectionId": parent_hex,
                    "conditionId": cond_hex,
                    "collateral": str(dec.get("collateral") or ""),
                    "partition": part,
                    "amount": int(dec.get("amount") or 0),
                }
                _append_debug(debug, f"[txhint] PositionSplit matched in receipt: parentCollectionId={parent_hex} collateral={out['collateral']} partition={part} amount={out['amount']}")
                return out
            except Exception:
                continue
        _append_debug(debug, f"[txhint] no PositionSplit matched in receipt: {txh}")
        return None
    except Exception as e:
        _append_debug(debug, f"[txhint] parse receipt failed: {e}")
        return None


def _try_any_positionsplit_from_tx_receipt(
    w3: Any,
    tx_hash_hex: str,
    ctf_addr: str,
    debug: List[str],
) -> List[Dict[str, Any]]:
    """
    诊断用：从给定 tx 的 receipt.logs 里提取所有 PositionSplit（不按 conditionId 过滤）。
    用于定位“你持有的 ERC1155 tokenId 实际属于哪个 conditionId/indexSet/collateral”。
    """
    out: List[Dict[str, Any]] = []
    try:
        txh = str(tx_hash_hex or "").strip()
        if not txh:
            return out
        if not txh.startswith("0x"):
            txh = "0x" + txh

        # keccak256("PositionSplit(address,address,bytes32,bytes32,uint256[],uint256)")
        topic0 = w3.keccak(text="PositionSplit(address,address,bytes32,bytes32,uint256[],uint256)").hex()
        if not topic0.startswith("0x"):
            topic0 = "0x" + topic0

        receipt = w3.eth.get_transaction_receipt(txh)
        logs = receipt.get("logs") if isinstance(receipt, dict) else getattr(receipt, "logs", None)
        if not logs:
            return out

        for lg in logs:
            try:
                addr = lg.get("address") if isinstance(lg, dict) else getattr(lg, "address", "")
                if str(addr).lower() != str(ctf_addr).lower():
                    continue
                topics_l = lg.get("topics") if isinstance(lg, dict) else getattr(lg, "topics", None)
                data_l = lg.get("data") if isinstance(lg, dict) else getattr(lg, "data", None)
                if not topics_l or len(topics_l) < 4:
                    continue
                if _to_hex32_topic(topics_l[0]).lower() != _to_hex32_topic(topic0).lower():
                    continue
                parent_hex = _to_hex32_topic(topics_l[2])
                cond_hex = _to_hex32_topic(topics_l[3])
                dec = _decode_positionsplit_data(w3, data_l, debug)
                if not dec:
                    continue
                part = dec.get("partition") or []
                out.append({
                    "tx_hash": txh,
                    "parentCollectionId": parent_hex,
                    "conditionId": cond_hex,
                    "collateral": str(dec.get("collateral") or ""),
                    "partition": [int(x) for x in (part or [])],
                    "amount": int(dec.get("amount") or 0),
                })
            except Exception:
                continue
        return out
    except Exception as e:
        _append_debug(debug, f"[txdiag] parse receipt(PositionSplit) failed: {e}")
        return out


def _onchain_find_ctf_params_by_positionsplit(
    w3: Any,
    ctf_addr: str,
    condition_id: str,
    stakeholders: List[str],
    index_set: int,
    debug: List[str],
) -> List[Dict[str, Any]]:
    """
    优先从链上 CTF PositionSplit 事件中反推出：
    - collateralToken（event data 里）
    - parentCollectionId（topic[2]，indexed）
    注意：stakeholder 是 indexed，可用来按 EOA / 交易所合约过滤。
    """
    cond = _normalize_hex32(condition_id)
    if not cond:
        return []
    try:
        # keccak256("PositionSplit(address,address,bytes32,bytes32,uint256[],uint256)")
        topic0 = w3.keccak(text="PositionSplit(address,address,bytes32,bytes32,uint256[],uint256)").hex()
        if not topic0.startswith("0x"):
            topic0 = "0x" + topic0
    except Exception as e:
        _append_debug(debug, f"build PositionSplit topic0 failed: {e}")
        return []

    # 扫描窗口（公共 RPC 常对 eth_getLogs 的 block range 有严格限制）
    # 经验：polygon-rpc.com 可能要求区块跨度非常小（甚至 < 2k），所以这里允许自适应缩小到几百/几千块。
    step = int(os.getenv("CTF_EVENT_SCAN_STEP", "50000") or 50000)          # 初始每次回看区块数
    max_steps = int(os.getenv("CTF_EVENT_SCAN_MAX_STEPS", "25") or 25)        # 最多回看窗口次数（不是总区块数）
    min_step = int(os.getenv("CTF_EVENT_SCAN_MIN_STEP", "1") or 1)            # 最小窗口（越小越稳但越慢）
    # 用户要求：step 最大不超过 50000，避免公共 RPC 因 range 过大直接拒绝 getLogs
    step = max(min_step, min(step, 50_000))
    max_steps = max(1, min(max_steps, 500))

    try:
        latest = int(w3.eth.block_number)
    except Exception as e:
        _append_debug(debug, f"read latest block failed: {e}")
        return []

    # 过滤掉非法地址
    stake_topics: List[str] = []
    for s in stakeholders or []:
        t = _topic_from_address(s)
        if t and t not in stake_topics:
            stake_topics.append(t)

    out: List[Dict[str, Any]] = []
    for st in stake_topics or [""]:
        # 用“滑动窗口”向后扫：窗口大小 step 可在过程中动态缩小
        to_block = int(latest)
        windows_done = 0
        cur_step = int(step)
        while to_block >= 0 and windows_done < max_steps:
            from_block = max(0, int(to_block - cur_step + 1))
            try:
                topics = [topic0, st if st else None, None, cond]
                logs = w3.eth.get_logs({
                    "address": w3.to_checksum_address(ctf_addr),
                    "fromBlock": int(from_block),
                    "toBlock": int(to_block),
                    "topics": topics,
                })
            except Exception as e:
                msg = str(e)
                _append_debug(debug, f"get_logs PositionSplit failed (from={from_block} to={to_block} step={cur_step} st={st[:10] if st else 'ANY'}): {msg}")
                # 典型：某些公共 RPC/归档节点裁剪了历史日志（pruned），getLogs 永远查不到
                msg_l = msg.lower()
                if ("pruned" in msg_l) or ("history has been pruned" in msg_l) or ("has been pruned" in msg_l):
                    _append_debug(
                        debug,
                        "[positionsplit] RPC 历史日志已被裁剪(pruned)/不可用，eth_getLogs 无法工作。"
                        "建议设置环境变量 POLYGONSCAN_API_KEY 改走 Polygonscan Logs API（或直接提供 TX_HASH_HINT/CTF_PARAMS_TX_HASH）。",
                    )
                    return []
                # 典型：polygon-rpc.com => Block range is too large / -32062
                if ("Block range is too large" in msg) or ("-32062" in msg):
                    if cur_step > min_step:
                        cur_step = max(min_step, int(cur_step / 2))
                        _append_debug(debug, f"reduce scan step => {cur_step}")
                        continue  # 用更小窗口重试同一段
                    # 已经缩到最小仍失败：说明这个 RPC 基本不可用（或彻底禁用了 getLogs）
                    _append_debug(
                        debug,
                        "[positionsplit] 当前 RPC 对 eth_getLogs 限制过严/不可用：即使 step 很小仍返回 Block range too large。"
                        "建议设置环境变量 POLYGON_RPC/RPC_URL 为支持 getLogs 的 RPC（Alchemy/QuickNode/Ankr/Infura 等），"
                        "或提供环境变量 CTF_PARAMS_TX_HASH 让脚本直接从交易回执解析参数。",
                    )
                    return []
                # 其他错误：直接跳过该窗口，避免死循环
                to_block = from_block - 1
                windows_done += 1
                continue

            if logs:
                _append_debug(debug, f"PositionSplit logs found: {len(logs)} (from={from_block} to={to_block} step={cur_step} st={st[:10] if st else 'ANY'})")
            for lg in logs or []:
                try:
                    topics_l = lg.get("topics") if isinstance(lg, dict) else getattr(lg, "topics", None)
                    data_l = lg.get("data") if isinstance(lg, dict) else getattr(lg, "data", None)
                    if not topics_l or len(topics_l) < 4:
                        continue
                    parent_hex = _to_hex32_topic(topics_l[2])
                    cond_hex = _to_hex32_topic(topics_l[3])
                    if cond_hex != cond:
                        continue
                    dec = _decode_positionsplit_data(w3, data_l, debug)
                    if not dec:
                        continue
                    part = dec.get("partition") or []
                    # 只保留和当前 OUTCOME(index_set) 相关的 split
                    if index_set and isinstance(part, list) and part and int(index_set) not in [int(x) for x in part]:
                        continue
                    out.append({
                        "parentCollectionId": parent_hex,
                        "conditionId": cond_hex,
                        "collateral": dec.get("collateral"),
                        "partition": part,
                        "amount": int(dec.get("amount") or 0),
                    })
                except Exception:
                    continue

            # 找到就不再往更早扫（够用了）
            if out:
                return out

            # 没找到：窗口向更早移动
            to_block = from_block - 1
            windows_done += 1

    return out


def _burn_redeem_positions(
    private_key: str,
    condition_id: str,
    token_id_int: int,
    index_set: int,
    debug: List[str],
    tx_hash_hint: str = "",
    api_key: str = "",
) -> Dict[str, Any]:
    if Web3 is None:
        raise RuntimeError("redeem 需要 web3.py：pip install web3")

    rpc = os.getenv('POLYGON_RPC') or os.getenv('RPC_URL')
    if not rpc:
        ak = str(api_key or "").strip()
        if ak:
            # 允许直接传完整 RPC URL；否则按 Alchemy key 拼接
            if ak.lower().startswith("http://") or ak.lower().startswith("https://"):
                rpc = ak
                _append_debug(debug, f"使用 API_KEY 输入作为 RPC_URL: {rpc}")
            else:
                rpc = f"https://polygon-mainnet.g.alchemy.com/v2/{ak}"
                _append_debug(debug, "未设置 POLYGON_RPC/RPC_URL，使用 API_KEY 拼接 Alchemy Polygon RPC")
    if not rpc:
        rpc = os.getenv('POLYGON_RPC_DEFAULT', 'https://rpc.ankr.com/polygon')
        _append_debug(debug, f"未设置 POLYGON_RPC/RPC_URL，使用默认 RPC: {rpc}")
    if not rpc:
        raise RuntimeError("缺少 RPC。请设置环境变量 POLYGON_RPC 或 RPC_URL（Polygon/137）")

    ctf_addr = os.getenv('CTF_ADDRESS', '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045')
    collateral = os.getenv("COLLATERAL_TOKEN")
    parent_collection_hex = os.getenv("PARENT_COLLECTION_ID")  # 可选：bytes32（0x + 64 hex）
    gamma_meta = None  # gamma lookup removed: rely on on-chain collateral probe
    # 即使用户手动设置了 collateral，也尝试从 gamma 拿 parentCollectionId（若用户没配置的话）
    if not parent_collection_hex and token_id_int and int(token_id_int) > 0:
        if gamma_meta is None:
            gamma_meta = _gamma_fetch_market_meta_by_clob_token_id(str(token_id_int), debug)
        if gamma_meta and isinstance(gamma_meta.get("parentCollectionId"), str):
            parent_collection_hex = str(gamma_meta.get("parentCollectionId"))
            _append_debug(debug, f"parentCollectionId 将使用 gamma 返回值: {parent_collection_hex}")
        # 若 token 反查失败，再用 condition 扫描尝试抓 parentCollectionId
        if not parent_collection_hex:
            m = _gamma_find_market_by_condition_id(condition_id, debug)
            if isinstance(m, dict):
                for k in ["parentCollectionId", "parent_collection_id", "parentCollectionID"]:
                    v = m.get(k)
                    if isinstance(v, str) and v.startswith("0x") and len(v) == 66:
                        parent_collection_hex = v
                        _append_debug(debug, f"parentCollectionId 将使用 gamma(condition) 返回值: {v}")
                        break
    chain_id = int(os.getenv('CHAIN_ID', '137'))
    req_timeout = int(os.getenv('POLYMARKET_TIMEOUT', '30'))
    redeem_timeout = int(os.getenv('REDEEM_TIMEOUT', '180'))

    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={'timeout': req_timeout}))
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
        # 读取型辅助函数（多数 ConditionalTokens/CTF 实现都带着它们）：
        # 用合约自身的实现来计算 collectionId/positionId，比本地手撸 keccak 更可靠（可规避“打包/顺序差异”）
        {
            'inputs': [
                {'internalType': 'bytes32', 'name': 'parentCollectionId', 'type': 'bytes32'},
                {'internalType': 'bytes32', 'name': 'conditionId', 'type': 'bytes32'},
                {'internalType': 'uint256', 'name': 'indexSet', 'type': 'uint256'},
            ],
            'name': 'getCollectionId',
            'outputs': [{'internalType': 'bytes32', 'name': '', 'type': 'bytes32'}],
            'stateMutability': 'pure',
            'type': 'function',
        },
        {
            'inputs': [
                {'internalType': 'address', 'name': 'collateralToken', 'type': 'address'},
                {'internalType': 'bytes32', 'name': 'collectionId', 'type': 'bytes32'},
            ],
            'name': 'getPositionId',
            'outputs': [{'internalType': 'uint256', 'name': '', 'type': 'uint256'}],
            'stateMutability': 'pure',
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

    cond = _normalize_hex32(condition_id)
    if not cond:
        raise ValueError("缺少 CONDITION_ID")

    # === 可选：用户给一个 tx_hash（比如 split/merge 那笔），直接从 receipt.logs 解析出 parentCollectionId/collateral ===
    tx_hint_in = str(tx_hash_hint or "").strip()
    if tx_hint_in:
        # 兼容：用户输入环境变量名（例如 TX_HASH_HINT），则取该环境变量值
        env_v = os.getenv(tx_hint_in)
        if isinstance(env_v, str) and env_v.strip():
            tx_hint_in = env_v.strip()
    tx_hint = tx_hint_in or (
        os.getenv("CTF_PARAMS_TX_HASH")
        or os.getenv("PARAMS_TX_HASH")
        or os.getenv("POSITION_SPLIT_TX_HASH")
        or os.getenv("TX_HASH_HINT")
        or ""
    ).strip()
    if tx_hint:
        _append_debug(debug, f"[txhint] using tx hash => {tx_hint}")
        hit = _try_params_from_tx_receipt(w3, tx_hint, ctf_addr, cond, int(index_set), debug)
        if hit:
            ph = str(hit.get("parentCollectionId") or "")
            ch = str(hit.get("collateral") or "")
            if ph.startswith("0x") and len(ph) == 66:
                parent_collection_hex = ph
                _append_debug(debug, f"[txhint] parentCollectionId(using) => {parent_collection_hex}")
            if ch.startswith("0x") and len(ch) == 42:
                collateral = ch
                _append_debug(debug, f"[txhint] collateral(using) => {collateral}")

    # === AUTO: Polygonscan 反查 tx_hash（不新增 Inputs，仅 env: POLYGONSCAN_API_KEY） ===
    # 条件：用户没给 tx_hint，且 parentCollectionId/collateral 都没补齐（否则不打扰用户的显式配置）
    if (not tx_hint) and (not parent_collection_hex) and (not collateral):
        txh_auto = _polygonscan_find_positionsplit_tx_hash(w3, ctf_addr, cond, debug)
        if txh_auto:
            hit2 = _try_params_from_tx_receipt(w3, txh_auto, ctf_addr, cond, int(index_set), debug)
            if hit2:
                ph = str(hit2.get("parentCollectionId") or "")
                col = str(hit2.get("collateral") or "")
                if ph.startswith("0x") and len(ph) == 66:
                    parent_collection_hex = ph
                    _append_debug(debug, f"[polygonscan] parentCollectionId(using) => {parent_collection_hex}")
                    _append_debug(debug, f"[txhint] parentCollectionId(from receipt) => {parent_collection_hex}")
                if col.startswith("0x") and len(col) == 42:
                    collateral = col
                    _append_debug(debug, f"[polygonscan] collateral(using) => {collateral}")
                    _append_debug(debug, f"[txhint] collateral(from receipt) => {collateral}")

    # 兜底：如果 logs API 因为条件维度查询不到，则按“我确实持有的 ERC1155 tokenId”去找相关 tx，再尝试从 receipt 解参
    if (not tx_hint) and (not parent_collection_hex) and (not collateral) and token_id_int and int(token_id_int) > 0:
        # token1155tx 命中 tx 可能只是转账，不含 PositionSplit；因此这里扫描多笔 tx，直到 receipt 能解析出 PositionSplit 参数
        txhs = _polygonscan_find_token1155_tx_hashes(
            wallet,
            ctf_addr,
            int(token_id_int),
            debug,
            max_hashes=int(os.getenv("POLYGONSCAN_1155_MAX_HASHES", "60") or 60),
        )
        for txh_auto2 in txhs or []:
            hit3 = _try_params_from_tx_receipt(w3, txh_auto2, ctf_addr, cond, int(index_set), debug)
            if not hit3:
                continue
            ph = str(hit3.get("parentCollectionId") or "")
            col = str(hit3.get("collateral") or "")
            if ph.startswith("0x") and len(ph) == 66:
                parent_collection_hex = ph
                _append_debug(debug, f"[polygonscan] parentCollectionId(using,1155) => {parent_collection_hex}")
                _append_debug(debug, f"[txhint] parentCollectionId(from receipt) => {parent_collection_hex}")
            if col.startswith("0x") and len(col) == 42:
                collateral = col
                _append_debug(debug, f"[polygonscan] collateral(using,1155) => {collateral}")
                _append_debug(debug, f"[txhint] collateral(from receipt) => {collateral}")
            if parent_collection_hex and collateral:
                break

    # === 优先从链上 PositionSplit 事件反推 collateral + parentCollectionId（比 gamma/猜测更靠谱）===
    # 注意：有些仓位在 CTF Exchange/NegRisk 等合约里托管，因此 stakeholder 不一定是 EOA。
    def _parse_addr_list(s: Any) -> List[str]:
        raw = str(s or "").strip()
        if not raw:
            return []
        parts = []
        for seg in raw.replace("\n", ",").replace(" ", ",").split(","):
            v = seg.strip()
            if v:
                parts.append(v)
        out2: List[str] = []
        seen = set()
        for v in parts:
            vv = v.strip()
            if vv.lower().startswith("0x") and len(vv) == 42:
                k = vv.lower()
                if k not in seen:
                    seen.add(k)
                    out2.append(vv)
        return out2

    DEFAULT_ESCROW_ADDRS = [
        os.getenv("CTF_EXCHANGE_ADDRESS", "").strip(),
        "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e",  # Polymarket: CTF Exchange（常见）
    ]
    escrow_env = (
        os.getenv("ESCROW_ADDRESSES")
        or os.getenv("POLYMARKET_ESCROW_ADDRESSES")
        or os.getenv("POLYMARKET_ESCROW_CONTRACTS")
        or ""
    )
    escrow_candidates: List[str] = []
    for a in _parse_addr_list(escrow_env) + _parse_addr_list(",".join(DEFAULT_ESCROW_ADDRS)):
        if a.lower() not in [x.lower() for x in escrow_candidates]:
            escrow_candidates.append(a)

    stakeholder_candidates = [wallet] + escrow_candidates
    ps_hits: List[Dict[str, Any]] = []
    # 只有当关键参数仍不全时，才尝试 eth_getLogs（公共 RPC 很可能 pruned/限制严格）
    if (not parent_collection_hex) or (not collateral):
        ps_hits = _onchain_find_ctf_params_by_positionsplit(w3, ctf_addr, cond, stakeholder_candidates, int(index_set), debug)
    if ps_hits:
        # 选一个“最像当前仓位”的：优先 amount 最大（通常是你 split 出仓位的那笔）
        ps_hits.sort(key=lambda x: int(x.get("amount", 0)), reverse=True)
        top = ps_hits[0]
        ps_parent = str(top.get("parentCollectionId") or "")
        ps_collat = str(top.get("collateral") or "")
        if ps_parent and ps_parent.startswith("0x") and len(ps_parent) == 66:
            parent_collection_hex = ps_parent
            _append_debug(debug, f"[positionsplit] parentCollectionId(onchain) => {parent_collection_hex}")
        if ps_collat and ps_collat.startswith("0x") and len(ps_collat) == 42:
            if collateral and collateral.lower() != ps_collat.lower():
                _append_debug(debug, f"[positionsplit] override collateral: {collateral} -> {ps_collat}")
            collateral = ps_collat
            _append_debug(debug, f"[positionsplit] collateral(onchain) => {collateral}")

    # 计算 CTF positionId（ERC1155 tokenId）：
    # collectionId = keccak256(parentCollectionId, conditionId, indexSet)
    # positionId  = uint256(keccak256(collateralToken, collectionId))
    # 注意：redeemPositions 不接收 tokenId，只接收 indexSets，因此用于 balanceOf 对比的应是“计算出来的 positionId”
    cond_bytes = bytes.fromhex(cond[2:])
    parent_collection = b'\x00' * 32
    if parent_collection_hex:
        try:
            pc = _normalize_hex32(parent_collection_hex)
            if pc and len(pc) == 66:
                parent_collection = bytes.fromhex(pc[2:])
                _append_debug(debug, f"parentCollectionId(using) => {pc}")
        except Exception as e:
            _append_debug(debug, f"parentCollectionId 解析失败（将使用 0x00..00）：{e}")

    # === MIN PATCH: auto-detect collateral token (USDC.e vs native USDC) ===
    USDC_E = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"   # bridged USDC.e
    USDC_NATIVE = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"  # native USDC
    PM_COLLATERAL = "0x3A3BD7bb9528E159577F7C2e685CC81A765002E2"  # <- 这笔仓位真实 collateral（你解 PositionSplit 得到的）

    # 先把“你当前兜底出来的 collateral”放到候选列表最前面
    collateral_candidates = []
    if collateral:
        collateral_candidates.append(collateral)
    # 若链上 positionsplit 找到了 collateral，也加入候选（避免某些数据不一致）
    try:
        for h in ps_hits or []:
            c0 = str((h or {}).get("collateral") or "").strip()
            if c0 and c0.lower().startswith("0x") and len(c0) == 42 and c0.lower() not in [x.lower() for x in collateral_candidates]:
                collateral_candidates.append(c0)
    except Exception:
        pass
    for c in [USDC_E, USDC_NATIVE, PM_COLLATERAL]:
        if c.lower() not in [x.lower() for x in collateral_candidates]:
            collateral_candidates.append(c)

    # 注意：不同 CTF/ConditionalTokens 实现对 positionId 的哈希可能存在“打包方式/顺序”差异。
    # 为了解决“balanceOf(PROVIDED_TOKEN_ID)>0 但用标准公式算出来 pid 余额为 0”的情况，这里做最小化自动探测：
    # - packed(address, collectionId)  (常见/标准)
    # - abi.encode(address, collectionId)（address 按 32 bytes 左补 0）
    # - 以及两者的顺序互换（极少数实现/包装合约可能这样做）
    def _calc_collection_id_local(ix: int) -> Any:
        # 标准 ConditionalTokens 公式：keccak256(abi.encodePacked(parentCollectionId, conditionId, indexSet))
        return w3.solidity_keccak(['bytes32', 'bytes32', 'uint256'], [parent_collection, cond_bytes, int(ix)])

    def _calc_collection_id(ix: int) -> Any:
        # 优先用合约自带 getCollectionId（若 ABI/实现存在），失败再退回本地 keccak
        try:
            if hasattr(ctf, "functions") and hasattr(ctf.functions, "getCollectionId"):
                return ctf.functions.getCollectionId(parent_collection, bytes.fromhex(cond[2:]), int(ix)).call()
        except Exception as e:
            _append_debug(debug, f"[pid] getCollectionId call failed, fallback to local keccak: {e}")
        return _calc_collection_id_local(ix)

    def _calc_pid_variants(collat_addr: str, ix: int) -> Dict[str, int]:
        """
        返回多个 positionId 计算候选：
        - 优先：合约 getPositionId(getCollectionId(...))（若可用）
        - 兜底：本地 keccak 的多种 packed/encode 与顺序组合（兼容极少数实现差异）
        """
        outv: Dict[str, int] = {}
        col_id = _calc_collection_id(ix)
        # col_id 是 bytes32
        cid_b = bytes(col_id) if isinstance(col_id, (bytes, bytearray)) else bytes.fromhex(str(col_id).replace("0x", ""))
        a = w3.to_checksum_address(collat_addr)
        a20 = bytes.fromhex(a[2:])
        a32 = (b"\x00" * 12) + a20

        # 1) 合约自带函数（最可靠）
        try:
            if hasattr(ctf, "functions") and hasattr(ctf.functions, "getPositionId"):
                pid_contract = int(ctf.functions.getPositionId(a, col_id).call())
                outv["ctf_getPositionId"] = int(pid_contract)
        except Exception as e:
            _append_debug(debug, f"[pid] getPositionId call failed, fallback to local keccak: {e}")

        # 2) 本地 keccak 组合（兜底）
        v1 = w3.keccak(a20 + cid_b)  # packed(address, bytes32)
        v2 = w3.keccak(a32 + cid_b)  # abi.encode(address, bytes32) => 32+32
        v3 = w3.keccak(cid_b + a20)  # swapped
        v4 = w3.keccak(cid_b + a32)  # swapped + padded
        outv.update({
            "packed_addr_then_cid": int.from_bytes(v1, "big", signed=False),
            "abi_addr32_then_cid": int.from_bytes(v2, "big", signed=False),
            "packed_cid_then_addr": int.from_bytes(v3, "big", signed=False),
            "abi_cid_then_addr32": int.from_bytes(v4, "big", signed=False),
        })
        return outv

    # 默认用标准 packed(address, collectionId)
    pid_mode = "packed_addr_then_cid"

    # 如果用户提供了 TOKEN_ID（且在该 ERC1155 上确实有余额），先尝试用它来锁定正确的哈希规则与 indexSet/collateral
    try:
        provided_token_id = int(token_id_int) if token_id_int is not None else None
    except Exception:
        provided_token_id = None

    def _calc_pid_for(collat_addr: str, ix: int, mode: Optional[str] = None) -> int:
        m = mode or pid_mode
        return _calc_pid_variants(collat_addr, ix).get(m) or _calc_pid_variants(collat_addr, ix)["packed_addr_then_cid"]

    best = None
    cand_debug = []
    # 1) 先用 provided_token_id 做“硬匹配”探测 mode/indexSet/collateral
    if provided_token_id is not None and provided_token_id > 0:
        for c in collateral_candidates:
            try:
                v_yes = _calc_pid_variants(c, 1)
                v_no = _calc_pid_variants(c, 2)
                for m, pid in v_yes.items():
                    if int(pid) == int(provided_token_id):
                        pid_mode = m
                        _append_debug(debug, f"[pid-mode] PROVIDED_TOKEN_ID matches YES under mode={m} collateral={c}")
                        break
                for m, pid in v_no.items():
                    if int(pid) == int(provided_token_id):
                        pid_mode = m
                        _append_debug(debug, f"[pid-mode] PROVIDED_TOKEN_ID matches NO under mode={m} collateral={c}")
                        break
            except Exception:
                continue

    # === PRE-PROBE DEBUG: print params + local pid compare (before [collateral-probe]) ===
    try:
        parent_disp = _normalize_hex32(parent_collection_hex) if parent_collection_hex else ("0x" + "0" * 64)
        _append_debug(
            debug,
            f"[pre-probe] params: conditionId={cond} parentCollectionId(using)={parent_disp} collateral(using)={collateral or ''} indexSet={int(index_set)}",
        )
        pid_local = None
        if collateral:
            # pid_local 使用“本地标准公式”：collectionId=keccak(abi.encodePacked(parent,condition,indexSet))
            # positionId=uint256(keccak256(abi.encodePacked(collateral(address20), collectionId(bytes32))))
            cid_local = _calc_collection_id_local(int(index_set))
            cid_b_local = bytes(cid_local) if isinstance(cid_local, (bytes, bytearray)) else bytes.fromhex(str(cid_local).replace("0x", ""))
            a = w3.to_checksum_address(collateral)
            a20 = bytes.fromhex(a[2:])
            pid_local = int.from_bytes(w3.keccak(a20 + cid_b_local), "big", signed=False)
        _append_debug(
            debug,
            f"[pre-probe] pid_local(packed_addr_then_cid + local_collection)={pid_local} provided_token_id={provided_token_id} => {'MATCH' if (pid_local is not None and provided_token_id is not None and int(pid_local)==int(provided_token_id)) else 'MISMATCH'}",
        )
    except Exception as e:
        _append_debug(debug, f"[pre-probe] debug print failed (ignore): {e}")

    # 2) 再按（collateral × mode）探测 YES/NO 余额，选出 score 最大者
    modes_to_try = [
        # 优先用合约自带 getPositionId（若可用）
        "ctf_getPositionId",
        "packed_addr_then_cid",
        "abi_addr32_then_cid",
        "packed_cid_then_addr",
        "abi_cid_then_addr32",
    ]
    for c in collateral_candidates:
        for m in modes_to_try:
            try:
                pid_y = _calc_pid_for(c, 1, mode=m)
                pid_n = _calc_pid_for(c, 2, mode=m)
                by = int(_with_retry(ctf.functions.balanceOf(wallet, pid_y).call, debug=debug, label=f"balanceOf(YES@{c[:6]}@{m[:6]})"))
                bn = int(_with_retry(ctf.functions.balanceOf(wallet, pid_n).call, debug=debug, label=f"balanceOf(NO@{c[:6]}@{m[:6]})"))
                cand_debug.append((c, m, pid_y, by, pid_n, bn))
                _append_debug(debug, f"[collateral-probe] {c} mode={m} => YES(pid={pid_y})={by}, NO(pid={pid_n})={bn}")
                score = by + bn
                if best is None or score > best["score"]:
                    best = {"collateral": c, "mode": m, "pid_yes": pid_y, "bal_yes": by, "pid_no": pid_n, "bal_no": bn, "score": score}
            except Exception as e:
                _append_debug(debug, f"[collateral-probe] {c} mode={m} failed: {e}")

    if best and best["score"] > 0:
        if (collateral or "").lower() != str(best["collateral"]).lower():
            _append_debug(debug, f"[collateral-picked] override collateral: {collateral} -> {best['collateral']}")
        collateral = best["collateral"]
        pid_mode = str(best.get("mode") or pid_mode)
        _append_debug(debug, f"[pid-mode] picked => {pid_mode}")

    # 如果两个 collateral 都算出来 YES/NO=0，就别发交易，直接返回（省 gas）
    if not best or best["score"] == 0:
        _append_debug(debug, "[collateral-picked] both collaterals give ZERO balance on EOA => probe escrow contracts")

        # 额外诊断：如果用户输入的 TOKEN_ID 本身就是 CTF positionId（ERC1155 id），这里能直接看到余额；
        # 这能区分“参数算错” vs “确实没仓位/在别的合约里记账”
        provided_token_id = int(token_id_int) if token_id_int is not None else None
        provided_diag: Dict[str, Any] = {}
        if provided_token_id is not None and provided_token_id > 0:
            try:
                pb = int(_with_retry(ctf.functions.balanceOf(wallet, int(provided_token_id)).call, debug=debug, label="balanceOf(PROVIDED_TOKEN_ID@EOA)"))
                provided_diag["provided_token_balance_eoa"] = int(pb)
                _append_debug(debug, f"[diag] balanceOf(wallet, PROVIDED_TOKEN_ID={provided_token_id}) => {pb}")
            except Exception as e:
                _append_debug(debug, f"[diag] balanceOf(PROVIDED_TOKEN_ID@EOA) failed: {e}")
            # 也查一下 escrow 合约里是否持有该 id（仅当用户的 tokenId 真的是 positionId 时有意义）
            escrow_bals: List[Dict[str, Any]] = []
            for holder in escrow_candidates or []:
                try:
                    holder_cs = w3.to_checksum_address(holder)
                    eb = int(_with_retry(ctf.functions.balanceOf(holder_cs, int(provided_token_id)).call, debug=debug, label=f"balanceOf(PROVIDED_TOKEN_ID@escrow@{holder[:6]})"))
                    if eb:
                        escrow_bals.append({"holder": holder, "balance": int(eb)})
                        _append_debug(debug, f"[diag] balanceOf(escrow={holder}, PROVIDED_TOKEN_ID={provided_token_id}) => {eb}")
                except Exception:
                    pass
            if escrow_bals:
                provided_diag["provided_token_balance_escrows"] = escrow_bals

        escrow_hits: List[Dict[str, Any]] = []
        if escrow_candidates and cand_debug:
            for holder in escrow_candidates:
                try:
                    holder_cs = w3.to_checksum_address(holder)
                except Exception as e:
                    _append_debug(debug, f"[escrow-probe] bad address {holder}: {e}")
                    continue
                # cand_debug 现在是 (collateral, mode, pid_y, by, pid_n, bn)
                for (c, m, pid_y, _by, pid_n, _bn) in cand_debug:
                    try:
                        ey = int(_with_retry(ctf.functions.balanceOf(holder_cs, int(pid_y)).call, debug=debug, label=f"balanceOf(YES@escrow@{holder[:6]}@{str(m)[:6]})"))
                        en = int(_with_retry(ctf.functions.balanceOf(holder_cs, int(pid_n)).call, debug=debug, label=f"balanceOf(NO@escrow@{holder[:6]}@{str(m)[:6]})"))
                        if ey or en:
                            escrow_hits.append({
                                "holder": holder,
                                "collateral": c,
                                "mode": m,
                                "pid_yes": int(pid_y),
                                "bal_yes": int(ey),
                                "pid_no": int(pid_n),
                                "bal_no": int(en),
                                "score": int(ey + en),
                            })
                            _append_debug(debug, f"[escrow-probe] holder={holder} collateral={c} mode={m} => YES(pid={pid_y})={ey}, NO(pid={pid_n})={en}")
                    except Exception as e:
                        _append_debug(debug, f"[escrow-probe] holder={holder} collateral={c} mode={m} failed: {e}")

        if escrow_hits:
            escrow_hits.sort(key=lambda x: int(x.get("score", 0)), reverse=True)
            top = escrow_hits[0]
            _append_debug(
                debug,
                f"[escrow-picked] FOUND tokens held by contract: holder={top.get('holder')} collateral={top.get('collateral')} "
                f"YES={top.get('bal_yes')} NO={top.get('bal_no')} (EOA=0). Need withdraw/unlock from escrow before redeemPositions.",
            )
            return {
                "tx_hash": "",
                "receipt_status": 0,
                "burned": 0,
                "ok": False,
                "pending": False,
                "skipped": True,
                "reason": "ESCROW_BALANCE_FOUND",
                "escrow_hits": escrow_hits[:20],
                "collateral_candidates": cand_debug,
                "condition_id": cond,
                "index_set": int(index_set),
            }

        _append_debug(debug, "[escrow-picked] no escrow balances found => skip redeemPositions")

        # === 进一步诊断：provided tokenId 明明有余额，但按当前 CONDITION_ID 推出来的 YES/NO positionId 全为 0 ===
        # 常见原因：用户输入的 CONDITION_ID 不对应这个 TOKEN_ID（TOKEN_ID 属于另一个 condition），
        # 或者 TOKEN_ID 并非 ConditionalTokens 的 positionId（例如某种包装/衍生 ERC1155 id）。
        try:
            pb = int((provided_diag or {}).get("provided_token_balance_eoa") or 0)
        except Exception:
            pb = 0
        txdiag: Dict[str, Any] = {}
        if provided_token_id is not None and provided_token_id > 0 and pb > 0:
            # 关键门道：wallet 的 token1155tx 很可能只有“转账”tx（receipt 不含 PositionSplit），
            # 真正的 PositionSplit 往往发生在别的地址（例如 CTF Exchange/托管合约），之后才转给你。
            # 所以这里做一个小型 BFS：沿 token1155tx 的 from/to 追溯到源头，直到找到包含 PositionSplit 的 tx。
            max_depth = int(os.getenv("TOKEN1155_TRACE_MAX_DEPTH", "5") or 5)
            max_depth = max(1, min(max_depth, 6))
            max_pages = int(os.getenv("POLYGONSCAN_1155_MAX_PAGES", "20") or 20)
            max_items = int(os.getenv("TOKEN1155_TRACE_MAX_ITEMS_PER_ADDR", "500") or 500)
            max_items = max(20, min(max_items, 1000))

            start_addrs: List[str] = [wallet]
            # 把常见交易所/托管合约也加入起点（即使没在余额里命中，也可能是历史来源）
            for a in (escrow_candidates or []):
                if a and a.lower().startswith("0x") and len(a) == 42 and a.lower() not in [x.lower() for x in start_addrs]:
                    start_addrs.append(a)

            queue: List[Dict[str, Any]] = [{"addr": a, "depth": 0} for a in start_addrs]
            seen_addr = set([a.lower() for a in start_addrs if isinstance(a, str)])
            seen_tx = set()
            matches: List[Dict[str, Any]] = []
            scanned: List[Dict[str, Any]] = []
            # 额外输出：把“你这枚 tokenId 的 token1155tx 转账明细”带回结果，便于用户手动在浏览器核对/把 tx_hash 当 TX_HASH_HINT 传入
            transfer_evidence: List[Dict[str, Any]] = []

            while queue and not matches:
                cur = queue.pop(0)
                addr = str(cur.get("addr") or "").strip()
                depth = int(cur.get("depth") or 0)
                if not (addr.lower().startswith("0x") and len(addr) == 42):
                    continue
                if depth > max_depth:
                    continue
                scanned.append({"addr": addr, "depth": depth})

                transfers = _polygonscan_fetch_token1155_transfers_for_tokenid(
                    addr,
                    ctf_addr,
                    int(provided_token_id),
                    debug,
                    max_pages=max_pages,
                    offset=None,
                    max_items=max_items,
                )
                # 记录：这个地址下看到的 tx 数量
                txdiag.setdefault("trace_scanned", []).append({"addr": addr, "depth": depth, "transfer_count": len(transfers)})
                # 收集少量证据：每个地址最多取前 10 条（按 API 返回通常是 desc）
                try:
                    for tr in (transfers or [])[:10]:
                        if isinstance(tr, dict) and tr.get("hash"):
                            transfer_evidence.append({
                                "addr": addr,
                                "depth": depth,
                                "hash": str(tr.get("hash") or ""),
                                "from": str(tr.get("from") or ""),
                                "to": str(tr.get("to") or ""),
                                "blockNumber": str(tr.get("blockNumber") or ""),
                                "timeStamp": str(tr.get("timeStamp") or ""),
                            })
                except Exception:
                    pass

                for tr in transfers or []:
                    txh = str(tr.get("hash") or "").strip()
                    if not txh.startswith("0x"):
                        continue
                    k = txh.lower()
                    if k in seen_tx:
                        continue
                    seen_tx.add(k)

                    ps_all = _try_any_positionsplit_from_tx_receipt(w3, txh, ctf_addr, debug)
                    if ps_all:
                        txdiag["positionsplit_tx_hash"] = txh
                        txdiag["positionsplit_events_in_tx"] = ps_all[:20]
                        # 尝试匹配 tokenId
                        for ev in ps_all or []:
                            try:
                                ev_parent = _normalize_hex32(ev.get("parentCollectionId"))
                                ev_cond = _normalize_hex32(ev.get("conditionId"))
                                ev_coll = str(ev.get("collateral") or "").strip()
                                ev_part = ev.get("partition") or []
                                if not (ev_parent and ev_cond and ev_coll.startswith("0x") and len(ev_coll) == 42):
                                    continue
                                parent_b = bytes.fromhex(ev_parent[2:])
                                cond_b = bytes.fromhex(ev_cond[2:])

                                for ix in [int(x) for x in (ev_part or []) if int(x) > 0]:
                                    col_id = w3.solidity_keccak(['bytes32', 'bytes32', 'uint256'], [parent_b, cond_b, int(ix)])
                                    cid_b = bytes(col_id) if isinstance(col_id, (bytes, bytearray)) else bytes.fromhex(str(col_id).replace("0x", ""))
                                    a = w3.to_checksum_address(ev_coll)
                                    a20 = bytes.fromhex(a[2:])
                                    a32 = (b"\x00" * 12) + a20
                                    variants: Dict[str, int] = {}
                                    # 合约自带（若可用）
                                    try:
                                        if hasattr(ctf, "functions") and hasattr(ctf.functions, "getPositionId") and hasattr(ctf.functions, "getCollectionId"):
                                            ccid = ctf.functions.getCollectionId(parent_b, cond_b, int(ix)).call()
                                            pidc = int(ctf.functions.getPositionId(w3.to_checksum_address(ev_coll), ccid).call())
                                            variants["ctf_getPositionId"] = int(pidc)
                                    except Exception:
                                        pass
                                    # 本地 keccak 兜底
                                    variants.update({
                                        "packed_addr_then_cid": int.from_bytes(w3.keccak(a20 + cid_b), "big", signed=False),
                                        "abi_addr32_then_cid": int.from_bytes(w3.keccak(a32 + cid_b), "big", signed=False),
                                        "packed_cid_then_addr": int.from_bytes(w3.keccak(cid_b + a20), "big", signed=False),
                                        "abi_cid_then_addr32": int.from_bytes(w3.keccak(cid_b + a32), "big", signed=False),
                                    })
                                    for m, pid in variants.items():
                                        if int(pid) == int(provided_token_id):
                                            matches.append({
                                                "conditionId": ev_cond,
                                                "parentCollectionId": ev_parent,
                                                "collateral": ev_coll,
                                                "indexSet": int(ix),
                                                "mode": m,
                                                "tx_hash": txh,
                                                "via_addr": addr,
                                            })
                            except Exception:
                                continue
                        if matches:
                            break

                    # 没有 PositionSplit：把 from/to 加入下一层追溯
                    if depth < max_depth:
                        for nxt in [str(tr.get("from") or "").strip(), str(tr.get("to") or "").strip()]:
                            if nxt.lower().startswith("0x") and len(nxt) == 42:
                                kk = nxt.lower()
                                if kk not in seen_addr:
                                    seen_addr.add(kk)
                                    queue.append({"addr": nxt, "depth": depth + 1})

                if matches:
                    break

            txdiag["token1155_trace_start_addresses"] = start_addrs
            txdiag["token1155_trace_max_depth"] = max_depth
            txdiag["token1155_trace_seen_tx"] = len(seen_tx)
            if transfer_evidence:
                # 限制返回体积：最多 60 条
                txdiag["token1155_transfer_evidence"] = transfer_evidence[:60]
                # 给用户一个最可能有用的 tx_hash：钱包地址 depth=0 的第一条 transfer
                try:
                    first_wallet = next((x for x in transfer_evidence if str(x.get("addr", "")).lower() == wallet.lower()), None)
                    if isinstance(first_wallet, dict) and str(first_wallet.get("hash") or "").startswith("0x"):
                        txdiag["suggested_tx_hash_hint"] = str(first_wallet.get("hash"))
                except Exception:
                    pass
            if matches:
                txdiag["provided_token_matches"] = matches[:10]
                _append_debug(debug, f"[txdiag] PROVIDED_TOKEN_ID matched PositionSplit params => {matches[0]}")
            else:
                _append_debug(debug, "[txdiag] no PositionSplit-derived params matched PROVIDED_TOKEN_ID via token1155 transfer tracing (increase TOKEN1155_TRACE_MAX_DEPTH/POLYGONSCAN_1155_MAX_PAGES)")
        if txdiag:
            provided_diag["token_id_tx_diagnosis"] = txdiag

        return {
            "tx_hash": "",
            "receipt_status": 0,
            "burned": 0,
            "ok": False,
            "pending": False,
            "skipped": True,
            "reason": "ZERO_BALANCE_FOR_ALL_COLLATERALS",
            "collateral_candidates": cand_debug,
            "escrow_candidates": escrow_candidates,
            "provided_token_diagnosis": provided_diag,
            "condition_id": cond,
            "index_set": int(index_set),
        }
    # === END PATCH ===

    provided_token_id = int(token_id_int) if token_id_int is not None else None
    provided_token_balance: Optional[int] = None
    if provided_token_id is not None and provided_token_id > 0:
        try:
            provided_token_balance = int(_with_retry(ctf.functions.balanceOf(wallet, int(provided_token_id)).call, debug=debug, label="balanceOf(PROVIDED_TOKEN_ID)"))
            _append_debug(debug, f"CTF balance(provided TOKEN_ID={provided_token_id}) => {provided_token_balance}")
        except Exception as e:
            _append_debug(debug, f"CTF balance(provided TOKEN_ID) failed (ignore): {e}")

    def _calc_position_id(ix: int, collateral_token: Optional[str] = None) -> int:
        # 统一使用上面自动探测出的 pid_mode（兼容少数实现的哈希差异）
        ctk = collateral_token or collateral
        return int(_calc_pid_for(ctk, int(ix)))

    position_id_expected = _calc_position_id(index_set)
    _append_debug(debug, f"positionId(expected) parent!=0?={bool(parent_collection_hex)} collateral={collateral} indexSet={index_set} => {position_id_expected}")

    # 若用户提供的 TOKEN_ID 与计算不一致，先尝试在常见 collateral 中匹配（很多市场是 USDC vs USDC.e 差异）
    if provided_token_id is not None and provided_token_id != position_id_expected:
        usdc_e = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
        usdc_native = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
        candidates: List[str] = []
        for c in [collateral, usdc_e, usdc_native, os.getenv("COLLATERAL_TOKEN_ALT", "")]:
            c = str(c or "").strip()
            if c and c not in candidates:
                candidates.append(c)
        matched = False
        for c in candidates:
            for ix in (1, 2):
                try:
                    pid = _calc_position_id(ix, c)
                except Exception:
                    continue
                if pid == provided_token_id:
                    matched = True
                    if c != collateral:
                        _append_debug(debug, f"TOKEN_ID 匹配到 collateral={c}（原 collateral={collateral}），将切换 collateral 以对齐 UI/抓取结果")
                        collateral = c
                    if ix != index_set:
                        _append_debug(debug, f"TOKEN_ID 匹配到 indexSet={ix}（原 indexSet={index_set}），将按 TOKEN_ID 纠正 indexSet")
                        index_set = ix
                    position_id_expected = pid
                    break
            if matched:
                break
        if not matched:
            _append_debug(
                debug,
                f"警告：TOKEN_ID={provided_token_id} 仍未能与当前 parentCollectionId/collateral/indexSet 计算结果匹配。"
                f"这通常意味着 parentCollectionId 非 0 且 gamma 未返回/或你抓取到的 token 不是 CTF positionId。"
            )

    # 额外打印 YES/NO 两侧余额，快速定位“选错 outcome / 没仓位 / tokenId 填错 / 参数未对齐”
    try:
        pid_yes = _calc_position_id(1)
        pid_no = _calc_position_id(2)
        bal_yes = int(_with_retry(ctf.functions.balanceOf(wallet, int(pid_yes)).call, debug=debug, label="balanceOf(YES)"))
        bal_no = int(_with_retry(ctf.functions.balanceOf(wallet, int(pid_no)).call, debug=debug, label="balanceOf(NO)"))
        _append_debug(debug, f"CTF balance snapshot: YES(pid={pid_yes})={bal_yes} | NO(pid={pid_no})={bal_no}")
        # 避免白花 gas：当 YES/NO 两侧余额都为 0 时，通常不需要发交易；
        # 但如果用户提供了 TOKEN_ID 且与 pid_yes/pid_no 不一致，说明参数可能没对齐（例如 parentCollectionId!=0），此时不要误判“无仓位”
        if bal_yes == 0 and bal_no == 0:
            if provided_token_id is not None and provided_token_id not in (int(pid_yes), int(pid_no)):
                _append_debug(debug, "YES=0 且 NO=0，但提供的 TOKEN_ID 与当前计算的 pid_yes/pid_no 不一致：更像是 parentCollectionId/collateral 参数未对齐，跳过发送并返回诊断信息")
                return {
                    'tx_hash': '',
                    'receipt_status': 0,
                    'burned': 0,
                    'provided_token_id': provided_token_id,
                    'position_id': int(position_id_expected),
                    'index_set': int(index_set),
                    'condition_id': cond,
                    'collateral': collateral,
                    'ctf': ctf_addr,
                    'ok': False,
                    'pending': False,
                    'skipped': True,
                    'reason': 'TOKEN_ID_MISMATCH_PARAMS',
                    'bal_yes': bal_yes,
                    'bal_no': bal_no,
                    'pid_yes': int(pid_yes),
                    'pid_no': int(pid_no),
                    'parentCollectionId': _normalize_hex32(parent_collection_hex) if parent_collection_hex else ("0x" + "0" * 64),
                    'provided_token_balance': provided_token_balance,
                }
            _append_debug(debug, "YES=0 且 NO=0：钱包在该 condition 下无任何 outcome token，跳过发送 redeemPositions（避免烧 gas）")
            return {
                'tx_hash': '',
                'receipt_status': 0,
                'burned': 0,
                'provided_token_id': provided_token_id,
                'position_id': int(position_id_expected),
                'index_set': int(index_set),
                'condition_id': cond,
                'collateral': collateral,
                'ctf': ctf_addr,
                'ok': False,
                'pending': False,
                'skipped': True,
                'reason': 'ZERO_BALANCE_BOTH_SIDES',
                'bal_yes': bal_yes,
                'bal_no': bal_no,
                'pid_yes': int(pid_yes),
                'pid_no': int(pid_no),
                'provided_token_balance': provided_token_balance,
            }
    except Exception as e:
        _append_debug(debug, f"CTF balance snapshot failed (ignore): {e}")
    if provided_token_id is not None and provided_token_id != position_id_expected:
        _append_debug(debug, f"提示：TOKEN_ID={provided_token_id} 与当前计算 positionId={position_id_expected} 仍不一致（可能 parentCollectionId 不同或 token 不是 CTF positionId）")

    before_bal = int(_with_retry(ctf.functions.balanceOf(wallet, int(position_id_expected)).call, debug=debug, label="balanceOf(before_expected)"))
    _append_debug(debug, f"CTF balance(before) positionId={position_id_expected} => {before_bal}")

    # 使用 pending nonce，避免与 mempool 中尚未打包的交易复用 nonce 导致 replacement underpriced
    try:
        nonce_pending = w3.eth.get_transaction_count(wallet, 'pending')
        nonce_latest = w3.eth.get_transaction_count(wallet, 'latest')
        _append_debug(debug, f"nonce: latest={nonce_latest} pending={nonce_pending}")
        nonce = nonce_pending
    except Exception as e:
        try:
            nonce = w3.eth.get_transaction_count(wallet)
            _append_debug(debug, f"nonce (fallback): {nonce}")
        except Exception:
            nonce = w3.eth.get_transaction_count(wallet)

    def _build_and_send_tx(tx_nonce: int, base_fee_mult: float = 1.0) -> Any:
        """构建并发送交易，支持 nonce 和费用倍数调整（用于 underpriced 重试）"""
        tx = ctf.functions.redeemPositions(
            w3.to_checksum_address(collateral),
            parent_collection,  # 重要：必须传真实 parentCollectionId（否则 parentCollectionId!=0 的市场永远 redeem 错）
            bytes.fromhex(cond[2:]),
            [int(index_set)],
        ).build_transaction({
            'from': wallet,
            'nonce': tx_nonce,
            'chainId': chain_id,
        })

        try:
            tx['gas'] = w3.eth.estimate_gas(tx)
        except Exception as e:
            _append_debug(debug, f"estimate_gas failed: {e}")
        
        # 费用策略（base_fee_mult 用于 underpriced 时自动提高费用）
        fee_mult = float(os.getenv('GAS_PRICE_MULTIPLIER', '1.20') or 1.20) * base_fee_mult
        fee_mult = max(1.0, min(fee_mult, 10.0))

        if 'gasPrice' not in tx and 'maxFeePerGas' not in tx:
            env_gas_gwei = os.getenv('GAS_PRICE_GWEI')
            env_max_fee_gwei = os.getenv('MAX_FEE_GWEI')
            env_prio_fee_gwei = os.getenv('PRIORITY_FEE_GWEI')
            try:
                if env_max_fee_gwei or env_prio_fee_gwei:
                    max_fee = int(float(env_max_fee_gwei or '0') * 1e9) if env_max_fee_gwei else None
                    prio_fee = int(float(env_prio_fee_gwei or '0') * 1e9) if env_prio_fee_gwei else None
                    if prio_fee is None or prio_fee <= 0:
                        prio_fee = int(30 * 1e9)
                    if max_fee is None or max_fee <= 0:
                        try:
                            pending_block = w3.eth.get_block('pending')
                            base_fee = int(getattr(pending_block, 'baseFeePerGas', 0) or 0)
                            max_fee = prio_fee + base_fee * 2
                        except Exception:
                            max_fee = prio_fee * 3
                    tx['maxPriorityFeePerGas'] = int(prio_fee * fee_mult)
                    tx['maxFeePerGas'] = int(max_fee * fee_mult)
                    _append_debug(debug, f"fees(EIP1559) mult={base_fee_mult:.2f}x maxFeePerGas={tx['maxFeePerGas']} maxPriorityFeePerGas={tx['maxPriorityFeePerGas']}")
                elif env_gas_gwei:
                    tx['gasPrice'] = int(float(env_gas_gwei) * 1e9 * fee_mult)
                    _append_debug(debug, f"fees(legacy) mult={base_fee_mult:.2f}x gasPrice={tx['gasPrice']}")
                else:
                    try:
                        pending_block = w3.eth.get_block('pending')
                        base_fee = int(getattr(pending_block, 'baseFeePerGas', 0) or 0)
                        if base_fee > 0:
                            prio_fee = int(30 * 1e9)
                            max_fee = prio_fee + base_fee * 2
                            tx['maxPriorityFeePerGas'] = int(prio_fee * fee_mult)
                            tx['maxFeePerGas'] = int(max_fee * fee_mult)
                            _append_debug(debug, f"fees(EIP1559-auto) mult={base_fee_mult:.2f}x baseFee={base_fee} maxFeePerGas={tx['maxFeePerGas']} maxPriorityFeePerGas={tx['maxPriorityFeePerGas']}")
                        else:
                            raise RuntimeError("pending block baseFeePerGas unavailable")
                    except Exception:
                        tx['gasPrice'] = int(w3.eth.gas_price * fee_mult)
                        _append_debug(debug, f"fees(legacy-auto) mult={base_fee_mult:.2f}x gasPrice={tx['gasPrice']}")
            except Exception as fee_e:
                _append_debug(debug, f"fees setup failed, continue without explicit fees: {fee_e}")

        signed = acct.sign_transaction(tx)
        raw_tx = _extract_signed_raw_tx(signed)
        return w3.eth.send_raw_transaction(raw_tx)

    # 发送交易，遇到 underpriced 时自动提高费用重试
    tx_hash = None
    max_retries = 3
    current_nonce = nonce
    for attempt in range(1, max_retries + 1):
        try:
            fee_multiplier = 1.0 if attempt == 1 else (2.0 ** (attempt - 1))  # 第1次1.0x，第2次2.0x，第3次4.0x
            # 重试时重新获取 nonce（如果旧交易被打包，可以用新 nonce 避免冲突）
            if attempt > 1:
                try:
                    new_pending = w3.eth.get_transaction_count(wallet, 'pending')
                    if new_pending > current_nonce:
                        current_nonce = new_pending
                        _append_debug(debug, f"检测到 nonce 已更新：{current_nonce}（旧交易可能已打包）")
                except Exception:
                    pass
            
            tx_hash = _build_and_send_tx(current_nonce, base_fee_mult=fee_multiplier)
            _append_debug(debug, f"redeemPositions tx sent (attempt {attempt}, nonce={current_nonce}) => {tx_hash.hex()}")
            break
        except Exception as e:
            err_msg = str(e).lower()
            if 'replacement transaction underpriced' in err_msg or 'underpriced' in err_msg:
                if attempt < max_retries:
                    next_mult = fee_multiplier * 2.0
                    _append_debug(debug, f"replacement underpriced (attempt {attempt}/{max_retries}, nonce={current_nonce})，下次将费用提高到 {next_mult:.1f}x 重试...")
                    time.sleep(1.0)  # 短暂等待，避免过快重试
                    continue
                else:
                    _append_debug(debug, f"replacement underpriced 重试{max_retries}次仍失败（nonce={current_nonce}）。可能原因：1) mempool 中有更高费用的 pending 交易占用此 nonce；2) RPC 负载均衡导致看到不同 mempool 视图。建议：等待旧交易上链/取消旧交易，或检查是否有其他脚本并发使用同一地址。")
                    raise
            else:
                # 非 underpriced 错误直接抛出
                raise
    if tx_hash is None:
        raise RuntimeError("发送交易失败：未能成功发送（未捕获到具体错误）")
    # 等回执：公共 RPC 可能负载均衡/短期不同后端，直接 wait_for_transaction_receipt 有时会误报超时。
    # 这里改为：轮询 get_transaction_receipt；超时则返回 pending 状态（不抛异常），把 tx_hash 交给上层输出。
    receipt = None
    ok = False
    pending = True
    try:
        from web3.exceptions import TransactionNotFound  # type: ignore
    except Exception:
        TransactionNotFound = None  # type: ignore

    start_ts = time.time()
    poll_s = float(os.getenv('RECEIPT_POLL_SECONDS', '3') or 3)
    poll_s = max(1.0, min(poll_s, 15.0))
    while True:
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            pending = False
            ok = int(getattr(receipt, 'status', 0)) == 1
            break
        except Exception as e:
            # 典型：TransactionNotFound / "not found" => 仍未上链
            if TransactionNotFound is not None and isinstance(e, TransactionNotFound):
                pass
            else:
                msg = str(e).lower()
                if 'not found' in msg or 'unknown transaction' in msg or 'transaction' in msg and 'not' in msg and 'found' in msg:
                    pass
                else:
                    # 非“未上链”类错误：记录但继续轮询，避免瞬时 RPC 故障导致直接失败
                    _append_debug(debug, f"get_transaction_receipt error (will retry): {e}")

        if time.time() - start_ts >= redeem_timeout:
            _append_debug(debug, f"等待回执超时（{redeem_timeout}s），交易可能仍在 pending 或被 RPC 丢失：{tx_hash.hex()}")
            break
        time.sleep(poll_s)

    after_bal = int(_with_retry(ctf.functions.balanceOf(wallet, int(position_id_expected)).call, debug=debug, label="balanceOf(after_expected)"))
    _append_debug(debug, f"CTF balance(after) positionId={position_id_expected} => {after_bal}")

    return {
        'tx_hash': tx_hash.hex(),
        'receipt_status': int(getattr(receipt, 'status', 0)) if receipt is not None else 0,
        'burned': max(0, before_bal - after_bal),
        'provided_token_id': provided_token_id,
        'position_id': int(position_id_expected),
        'index_set': int(index_set),
        'condition_id': cond,
        'collateral': collateral,
        'ctf': ctf_addr,
        'ok': bool(ok),
        'pending': bool(pending),
    }


def run_node(node):
    Debugging: List[str] = []

    def _get_input(idx: int):
        try:
            return node['Inputs'][idx]['Context']
        except Exception:
            return None

    private_key_input = str(_get_input(0) or "").strip()
    if private_key_input:
        env_value = os.getenv(private_key_input)
        private_key = env_value if env_value else private_key_input
    else:
        private_key = ""

    condition_id = str(_get_input(1) or "").strip()
    token_id = str(_get_input(2) or "").strip()
    outcome = str(_get_input(3) or "").strip()
    tx_hash_hint = str(_get_input(4) or "").strip()

    api_key_input = str(_get_input(5) or "").strip()
    if api_key_input:
        env_value = os.getenv(api_key_input)
        api_key = env_value if env_value else api_key_input
    else:
        api_key = ""

    tx_hash_out = ""
    success_out = False
    result: Dict[str, Any] = {"success": False}

    try:
        if not private_key:
            raise ValueError("缺少 PRIVATE_KEY")
        if not condition_id:
            raise ValueError("缺少 CONDITION_ID")
        # TOKEN_ID 仅用于校验/展示；redeemPositions 实际按 conditionId+indexSet 赎回，因此允许为空。
        token_id_int: Optional[int] = None
        if token_id:
            token_id_int = int(token_id)
        else:
            _append_debug(Debugging, "提示：未提供 TOKEN_ID，将自动按 conditionId+OUTCOME 计算 positionId 并据此计算 burned")

        index_set = _resolve_index_set(outcome)

        burn_info = _burn_redeem_positions(
            private_key,
            condition_id,
            int(token_id_int or 0),
            index_set,
            Debugging,
            tx_hash_hint=tx_hash_hint,
            api_key=api_key,
        )
        tx_hash_out = str(burn_info.get('tx_hash') or "")

        burned = int(burn_info.get('burned') or 0)
        ok = bool(burn_info.get('ok'))
        success_out = bool(ok and burned > 0)

        result.update({
            "success": bool(ok),
            "action": "REDEEM",
            "token_id": str(token_id_int or ""),
            "outcome": outcome,
            "burn": burn_info,
            "note": (
                "redeem 交易成功但 burned=0：通常表示该 outcome 的 positionId 余额为 0（已卖光/已赎回/选错 OUTCOME），或你填写的 TOKEN_ID 与计算出的 positionId 不一致。"
                if ok and burned == 0 else
                ("交易仍在 pending，稍后可用 TxHash 查询/加速/取消" if bool(burn_info.get('pending')) else "")
            ),
        })

        Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False)
        Outputs[2]['Context'] = "true" if success_out else "false"
        Outputs[3]['Context'] = tx_hash_out
    except Exception as e:
        Outputs[0]['Context'] = json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
        _append_debug(Debugging, f"ERROR => {e}")
        Outputs[2]['Context'] = "false"
        Outputs[3]['Context'] = ""

    Outputs[1]['Context'] = "\n".join(Debugging)
    return Outputs


