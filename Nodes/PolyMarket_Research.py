import json
import logging
import os
import re
import requests
import time

# **Function definition**

# **Define the number of outputs and inputs**输入节点与输出节点的数量
OutPutNum = 3
InPutNum = 1

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [
    {'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}',
     'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''}
    for i in range(OutPutNum)
]
Inputs  = [
    {'Num': None, 'Kind': None, 'Id': f'Input{i + 1}',  'Context': None,
     'Isnecessary': True, 'name': f'Input{i + 1}',  'Link': 0, 'IsLabel': True}
    for i in range(InPutNum)
]

NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个基础的节点模板程序，用于创建具有单一输入和输出的处理节点，可以根据需求自定义输入输出属性和处理逻辑。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n程序定义了一个标准的节点结构模板，包含输入输出节点的初始化、属性配置和基础的运行框架。核心处理逻辑在run_node函数中实现，当前版本仅提供框架结构，具体业务逻辑需要根据实际需求进行填充。\\n\\n参数\\n```yaml\\ninputs:\\n  - name: Input1\\n    type: string\\n    required: true\\n    description: 输入数据内容\\noutputs:\\n  - name: OutPut1\\n    type: string\\n    description: 处理后的输出结果\\n```\\n\\n运行逻辑（用 - 列表描写详细流程）\\n- 程序启动时定义输入输出节点数量，当前设置为各1个\\n- 初始化输入输出数组，为每个节点分配基础属性包括ID、名称、类型等\\n- 配置节点类型为Normal，设置标签属性Label1\\n- 为所有输入输出节点指定数据类型为String\\n- 执行run_node函数时获取输入节点的Context内容作为file_path\\n- 初始化content变量用于存储处理结果，初始化Debugging列表用于调试信息收集\\n- 将处理后的content内容赋值给输出节点的Context属性\\n- 返回包含处理结果的Outputs数组'

# **Assign properties to Inputs/Outputs**
for o in Outputs:
    o['Kind'] = 'String'
for i in Inputs:
    i['Kind'] = 'String'

# 输入
Inputs[0]['Kind'] = 'String'
Inputs[0]['name'] = 'Token_Id'
Inputs[0]['Isnecessary'] = True
Inputs[0]['IsLabel'] = False

# 输出
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Ask_Price'
Outputs[1]['Kind'] = 'String'
Outputs[1]['name'] = 'Bids_Price'
Outputs[2]['Kind'] = 'String'
Outputs[2]['name'] = 'Debug'

# ====== 取价最小依赖 ======
SESS = requests.Session()
SESS.headers.update({"User-Agent": "pm-screen/1.0"})
CLOB = "https://clob.polymarket.com"

def get_price(token_id: str, side: str = "BUY", retry: int = 3, timeout: int = 8, debug: list | None = None, pause: float = 0.5):
    """
    返回 float 或 None
    side:
      - 'BUY'  -> 最优卖价(ask)    —— 买入要付的价格
      - 'SELL' -> 最优买价(bid)    —— 卖出能拿的价格
    """
    token_id = (token_id or "").strip()
    if not token_id:
        if debug is not None:
            debug.append(f"[skip] token_id 为空，side={side}")
        return None

    side = side.upper()
    if side not in ("BUY", "SELL"):
        side = "BUY"

    # 首选：/price
    for attempt in range(1, retry + 1):
        try:
            r = SESS.get(f"{CLOB}/price", params={"token_id": token_id, "side": side}, timeout=timeout)
            if debug is not None:
                debug.append(f"[/price] attempt={attempt} side={side} status={r.status_code}")
            if r.status_code == 200:
                js = r.json() or {}
                if js.get("price") is not None:
                    if debug is not None:
                        debug.append(f"[/price] success side={side} price={js.get('price')}")
                    return float(js["price"])
                else:
                    if debug is not None:
                        debug.append(f"[/price] body_without_price side={side} body_type={type(js).__name__}")
            else:
                if debug is not None:
                    debug.append(f"[/price] non200 side={side} status={r.status_code}")
        except Exception as e:
            if debug is not None:
                debug.append(f"[/price] exception side={side} {type(e).__name__}: {e}")
        time.sleep(pause)

    # 兜底：/prices（批量）
    for attempt in range(1, retry + 1):
        try:
            payload = [{"token_id": token_id, "side": side}]
            r = SESS.post(f"{CLOB}/prices", json=payload, timeout=timeout)
            if debug is not None:
                debug.append(f"[/prices] attempt={attempt} side={side} status={r.status_code}")
            if r.status_code == 200:
                js = r.json() or []
                if isinstance(js, list) and js:
                    p = js[0].get("price")
                    if p is not None:
                        if debug is not None:
                            debug.append(f"[/prices] success(list) side={side} price={p}")
                        return float(p)
                    else:
                        if debug is not None:
                            debug.append(f"[/prices] list_without_price side={side}")
                elif isinstance(js, dict):
                    v = js.get(token_id) or {}
                    if isinstance(v, dict) and v.get("price") is not None:
                        if debug is not None:
                            debug.append(f"[/prices] success(dict) side={side} price={v.get('price')}")
                        return float(v["price"])
                    else:
                        if debug is not None:
                            debug.append(f"[/prices] dict_without_price side={side}")
                else:
                    if debug is not None:
                        debug.append(f"[/prices] unexpected_body_type side={side} body_type={type(js).__name__}")
            else:
                if debug is not None:
                    debug.append(f"[/prices] non200 side={side} status={r.status_code}")
        except Exception as e:
            if debug is not None:
                debug.append(f"[/prices] exception side={side} {type(e).__name__}: {e}")
        time.sleep(pause)

    if debug is not None:
        debug.append(f"[result] 未获取到价格 side={side}")
    return None
# ========================

# **Function definition**
def run_node(node):
    token_id = node['Inputs'][0].get('Context') or ""

    # 可选：同时取最优卖价(ask)与最优买价(bid)
    debug_lines = []
    debug_lines.append(f"[start] token_id={token_id.strip()}")
    ask_price = get_price(token_id, side="BUY", retry=3, timeout=8, debug=debug_lines)
    bid_price = get_price(token_id, side="SELL", retry=3, timeout=8, debug=debug_lines)
    debug_lines.append(f"[final] ask_price={('None' if ask_price is None else f'{ask_price:.4f}')}, bid_price={('None' if bid_price is None else f'{bid_price:.4f}')}")

    Outputs[0]['Context'] = "" if bid_price is None else f"{bid_price:.2f}"
    Outputs[1]['Context'] = "" if ask_price is None else f"{ask_price:.2f}"
    Outputs[2]['Context'] = "\n".join(debug_lines)

    return Outputs
# **Function definition**
