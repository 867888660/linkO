import json
import logging
import os
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, List, Dict, Any

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
OutPutNum = 4
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
    '这是一个基础的节点模板程序，用于在 Polymarket CLOB 上执行限价下单、撤单操作。节点读取 Mode、PRICE、SIZE_SHARES、TIME_IN_FORCE_MODE、'
    'PRIVATE_KEY、TOKEN_ID、HOST、CHAIN_ID 等输入，输出 Result（JSON 字符串）与 DeBugging（调试信息文本）。\n\n'
    '代码功能摘要（概括核心算法或主要处理步骤）\n'
    '程序定义了标准的节点结构，初始化输入输出节点数组并设置属性。核心处理逻辑在 run_node 函数中实现：根据 Mode 选择下单或撤单流程，完成 API 凭据生成、构建订单对象、发送订单或执行撤单操作，将结果与调试日志写入输出。\n\n'
    '参数\n```yaml\n'
    'inputs:\n'
    '  - name: Mode\n    type: string\n    required: true\n    description: 操作模式（BUY | SELL | WITHDRAW_ORDER）\n'
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
    '  - name: OrderID\n    type: string\n    description: 下单成功返回的订单ID（失败为空字符串）\n```\n'
    '\n运行逻辑（用 - 列表描写详细流程）\n'
    '- 初始化输入输出节点数组，并设置节点属性（ID、名称、类型等）\n'
    '- 解析输入参数 Context，包括 Mode、PRICE、SIZE_SHARES 等\n'
    '- 构建 ClobClient 客户端，生成并设置 L2 API 凭据\n'
    '- 根据 Mode 执行不同流程：BUY/SELL 时创建并发送订单；WITHDRAW_ORDER 时列举并取消匹配挂单\n'
    '- 收集结果数据和调试信息，赋值到输出节点 Context（含 Success、OrderID）\n'
    '- 返回包含 Result 和 DeBugging 的 Outputs 数组'
)


def _append_debug(debug_list: List[str], message: str) -> None:
    debug_list.append(message)
    try:
        logging.info(message)
        print(message)
    except Exception:
        pass


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
    return max(0.5, delay)


def _with_retry(fn, *args, debug: Optional[List[str]] = None, label: str = '', retry_on_unsuccess: bool = False, **kwargs):
    last_exc = None
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
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
            if attempt >= RETRY_MAX_ATTEMPTS:
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
    # Polymarket 常见价格范围在 (0, 1]，并且最小步长为 0.001（用户反馈/更细报价）
    if price_dec <= 0 or price_dec > 1:
        raise ValueError(f"PRICE 必须在 (0, 1] 之间，收到: {price}")
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
    host = str(_get_input(6) or os.getenv("HOST", "https://clob.polymarket.com"))
    chain_id = int(_get_input(7) or os.getenv("CHAIN_ID", 137))

    try:
        if not private_key:
            raise ValueError("缺少 PRIVATE_KEY")
        if not token_id:
            raise ValueError("缺少 TOKEN_ID")

        tif_mode = int(float(tif_in)) if tif_in not in (None, "") else 0
        tif = _resolve_tif(tif_mode)

        client = _build_client(private_key, host, chain_id)
        _try_set_timeout(client, REQUEST_TIMEOUT_SECONDS, Debugging)
        ok_val = _with_retry(client.get_ok, debug=Debugging, label="get_ok")
        _append_debug(Debugging, f"GET /ok -> {ok_val}")
        # 凭据创建使用原始逻辑，避免不必要的改动与参数不匹配
        _create_or_set_creds(client, Debugging)
        _append_debug(Debugging, f"wallet: {Account.from_key(private_key).address}")

        result: Dict[str, object] = {"success": False}
        order_id_out: str = ""
        success_out: bool = False

        if mode in ("BUY", "SELL"):
            if not price:
                raise ValueError("BUY/SELL 需要 PRICE")
            if not size:
                raise ValueError("BUY/SELL 需要 SIZE_SHARES")
            _validate_for_order(mode, price, float(size))
            # 统一将价格规范到三位小数，避免浮点误差导致的步长/过滤问题
            price_norm = Decimal(str(price)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
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
        else:
            raise ValueError("Mode 必须是 BUY、SELL 或 WITHDRAW_ORDER")

        Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False)
        Outputs[2]['Context'] = "true" if success_out else "false"
        Outputs[3]['Context'] = order_id_out
    except Exception as e:
        err_msg = str(e)
        Outputs[0]['Context'] = json.dumps({"success": False, "error": err_msg}, ensure_ascii=False)
        _append_debug(Debugging, f"ERROR => {e}")
        low = err_msg.lower()
        if ("not enough balance" in low) or ("allowance" in low):
            _append_debug(Debugging, "诊断：余额或授权不足。")
            _append_debug(Debugging, "建议：")
            _append_debug(Debugging, "- SELL：确保钱包中持有足够的该 outcome token，或准备按空头方式卖出时钱包内有足够 USDC 抵押；")
            _append_debug(Debugging, "- 授权：给撮合/结算合约授权 outcome token/USDC（可在前端或通过 SDK 调用 set/ensure allowance）；")
            _append_debug(Debugging, "- 网络：确认当前链 ID 与主机配置正确（如 Polygon 主网 137 与 https://clob.polymarket.com）。")
        Outputs[2]['Context'] = "false"
        Outputs[3]['Context'] = ""

    Outputs[1]['Context'] = "\n".join(Debugging)
    return Outputs
