import json
import logging
import os
import time
from typing import Optional, List, Dict, Any

# 可选：链上 redeem（需要 web3.py）。若缺失则在运行时给出友好提示。
try:
    from web3 import Web3  # type: ignore
except Exception:
    Web3 = None  # type: ignore

# **节点输入输出定义**
OutPutNum = 4
InPutNum = 4
NodeKind = 'Normal'

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]

_input_names = [
    'PRIVATE_KEY',
    'CONDITION_ID',
    'TOKEN_ID',
    'OUTCOME',  # YES/NO
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
    '节点仅保留必要 Inputs：PRIVATE_KEY、CONDITION_ID、TOKEN_ID、OUTCOME。运行时读取 RPC/合约地址等环境变量，'
    '调用 CTF redeemPositions 后用 balanceOf 前后对比计算 burned，burned>0 视为确实销毁成功。\n\n'
    '参数\n```yaml\n'
    'inputs:\n'
    '  - name: PRIVATE_KEY\n    type: string\n    required: true\n    description: 钱包私钥（0x... 或环境变量名）\n'
    '  - name: CONDITION_ID\n    type: string\n    required: true\n    description: CTF conditionId（bytes32，0x... 64 hex）\n'
    '  - name: TOKEN_ID\n    type: string\n    required: true\n    description: CTF position token id（uint256，通常与 clobTokenIds 对应）\n'
    '  - name: OUTCOME\n    type: string\n    required: true\n    description: YES/NO（或 1/2，对应二元 indexSet bitmask）\n'
    'outputs:\n'
    '  - name: Result\n    type: string\n    description: 返回结果 JSON 字符串\n'
    '  - name: DeBugging\n    type: string\n    description: 调试日志，多行文本\n'
    '  - name: Success\n    type: string\n    description: 判定完成（tx 成功且 burned>0）时为 true，否则 false\n'
    '  - name: TxHash\n    type: string\n    description: 交易哈希（失败为空字符串）\n```\n'
    '\n环境变量（不新增 Inputs）\n'
    '- POLYGON_RPC 或 RPC_URL：Polygon(137) RPC（未设置则默认 https://polygon-rpc.com，可用 POLYGON_RPC_DEFAULT 覆盖默认）\n'
    '- CTF_ADDRESS：CTF 合约地址（默认 0x4D97...6045）\n'
    '- COLLATERAL_TOKEN：抵押品 token（默认 0x2791...4174，USDC.e）\n'
    '- CHAIN_ID：默认 137\n'
    '- REDEEM_TIMEOUT：等待回执超时秒数（默认 180）\n'
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


def _burn_redeem_positions(private_key: str, condition_id: str, token_id_int: int, index_set: int, debug: List[str]) -> Dict[str, Any]:
    if Web3 is None:
        raise RuntimeError("redeem 需要 web3.py：pip install web3")

    rpc = os.getenv('POLYGON_RPC') or os.getenv('RPC_URL')
    if not rpc:
        rpc = os.getenv('POLYGON_RPC_DEFAULT', 'https://polygon-rpc.com')
        _append_debug(debug, f"未设置 POLYGON_RPC/RPC_URL，使用默认 RPC: {rpc}")
    if not rpc:
        raise RuntimeError("缺少 RPC。请设置环境变量 POLYGON_RPC 或 RPC_URL（Polygon/137）")

    ctf_addr = os.getenv('CTF_ADDRESS', '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045')
    collateral = os.getenv('COLLATERAL_TOKEN', '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174')
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

    before_bal = int(_with_retry(ctf.functions.balanceOf(wallet, int(token_id_int)).call, debug=debug, label="balanceOf(before)"))
    _append_debug(debug, f"CTF balance(before) token_id={token_id_int} => {before_bal}")

    cond = _normalize_hex32(condition_id)
    if not cond:
        raise ValueError("缺少 CONDITION_ID")

    tx = ctf.functions.redeemPositions(
        w3.to_checksum_address(collateral),
        b'\x00' * 32,
        bytes.fromhex(cond[2:]),
        [int(index_set)],
    ).build_transaction({
        'from': wallet,
        'nonce': w3.eth.get_transaction_count(wallet),
        'chainId': chain_id,
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
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=redeem_timeout)
    ok = int(getattr(receipt, 'status', 0)) == 1

    after_bal = int(_with_retry(ctf.functions.balanceOf(wallet, int(token_id_int)).call, debug=debug, label="balanceOf(after)"))
    _append_debug(debug, f"CTF balance(after) token_id={token_id_int} => {after_bal}")

    return {
        'tx_hash': tx_hash.hex(),
        'receipt_status': int(getattr(receipt, 'status', 0)),
        'burned': max(0, before_bal - after_bal),
        'index_set': int(index_set),
        'condition_id': cond,
        'collateral': collateral,
        'ctf': ctf_addr,
        'ok': bool(ok),
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

    tx_hash_out = ""
    success_out = False
    result: Dict[str, Any] = {"success": False}

    try:
        if not private_key:
            raise ValueError("缺少 PRIVATE_KEY")
        if not condition_id:
            raise ValueError("缺少 CONDITION_ID")
        if not token_id:
            raise ValueError("缺少 TOKEN_ID")

        token_id_int = int(token_id)
        index_set = _resolve_index_set(outcome)

        burn_info = _burn_redeem_positions(private_key, condition_id, token_id_int, index_set, Debugging)
        tx_hash_out = str(burn_info.get('tx_hash') or "")

        burned = int(burn_info.get('burned') or 0)
        ok = bool(burn_info.get('ok'))
        success_out = bool(ok and burned > 0)

        result.update({
            "success": bool(ok),
            "action": "REDEEM",
            "token_id": str(token_id_int),
            "outcome": outcome,
            "burn": burn_info,
            "note": ("redeem tx 成功但本次未烧掉任何 token：可能未到可领取阶段 / 不是赢方 / 余额为0" if ok and burned == 0 else ""),
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


