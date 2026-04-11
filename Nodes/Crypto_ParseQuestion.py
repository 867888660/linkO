"""
Crypto_ParseQuestion - LLM解析加密货币相关问题
从自然语言问题中智能提取：加密货币代码、Binance交易对、目标价格、方向、时间条件
"""

import json
import os
import httpx
from pathlib import Path
from typing import Any

# ========== 节点基础信息 ==========
OutPutNum = 2
InPutNum = 2

Outputs = [
    {'Num': None, 'Kind': 'String', 'Boolean': False, 'Id': 'Output1', 'Context': None, 'name': 'parsed_json', 'Link': 0, 'Description': '解析后的JSON'},
    {'Num': None, 'Kind': 'String', 'Boolean': False, 'Id': 'Output2', 'Context': None, 'name': 'binance_symbol', 'Link': 0, 'Description': 'Binance交易对符号'}
]

Inputs = [
    {'Num': None, 'Kind': 'String', 'Id': 'Input1', 'Context': None, 'name': 'question', 'Link': 0, 'IsLabel': False, 'Isnecessary': True},
    {'Num': None, 'Kind': 'Trigger', 'Id': 'Input_Trigger_IsCrypto', 'Context': None, 'name': 'IsCrypto_Trigger', 'Link': 0, 'IsLabel': False, 'Isnecessary': False}
]

NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

FunctionIntroduction = (
    "组件功能\n"
    "加密货币问题解析节点：使用LLM从自然语言问题中智能提取加密货币代码、目标价格、方向、时间条件。\n\n"
    "参数\n```yaml\n"
    "inputs:\n"
    "  - name: question\n    type: string\n    required: true\n    description: 用户问题，如'Bitcoin能涨到15万吗？'\n"
    "outputs:\n"
    "  - name: parsed_json\n    type: string\n    description: 解析结果JSON，包含symbol/binance_symbol/target_price/direction等\n"
    "  - name: binance_symbol\n    type: string\n    description: Binance交易对符号，如BTCUSDT\n```"
)


def get_llm_api_key():
    component_name = Path(__file__).stem
    try:
        edit_path = Path(__file__).parent.parent / "Edit" / "Edit.json"
        if edit_path.exists():
            with open(edit_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                llm_mappings = config.get('llmMappings', {})
                key_name = None
                for k, v in llm_mappings.items():
                    if k.lower() == component_name.lower():
                        key_name = v
                        break
                if key_name:
                    api_key = os.getenv(key_name, "")
                    if api_key:
                        return api_key
                    else:
                        raise ValueError(f"环境变量 '{key_name}' 未设置，组件: {component_name}")
                else:
                    raise ValueError(f"组件 '{component_name}' 未在 llmMappings 中配置")
    except Exception as e:
        raise ValueError(f"读取密钥配置失败: {e}")
    raise ValueError(f"无法获取组件 '{component_name}' 的 API 密钥")


def _llm_parse_question(question: str) -> dict:
    api_key = get_llm_api_key()
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    system_prompt = """你是一个专业的加密货币市场问题解析助手。你需要从用户的问题中提取以下信息：

1. **symbol**: 加密货币代码（如 BTC, ETH, SOL, DOGE 等）
2. **binance_symbol**: Binance交易对格式（如 BTCUSDT, ETHUSDT, SOLUSDT）
3. **target_price**: 目标价格（数字，如果问题中没有具体价格则为 null）
4. **direction**: 价格方向（"above" 表示看涨/突破/达到，"below" 表示看跌/跌破）
5. **time_condition**: 时间条件描述（如 "by December 31, 2026"，没有则为 null）

**常见加密货币名称/别名到代码的映射**：
- 比特币/Bitcoin → BTC (BTCUSDT)
- 以太坊/Ethereum/Ether → ETH (ETHUSDT)
- 索拉纳/Solana → SOL (SOLUSDT)
- 瑞波/Ripple/XRP → XRP (XRPUSDT)
- 狗狗币/Dogecoin → DOGE (DOGEUSDT)
- 卡达诺/Cardano → ADA (ADAUSDT)
- 雪崩/Avalanche → AVAX (AVAXUSDT)
- 波卡/Polkadot → DOT (DOTUSDT)
- Chainlink → LINK (LINKUSDT)
- Polygon/MATIC → MATIC (MATICUSDT)
- 莱特币/Litecoin → LTC (LTCUSDT)
- 币安币/BNB → BNB (BNBUSDT)
- SHIBA → SHIB (SHIBUSDT)
- 波场/TRON → TRX (TRXUSDT)
- Uniswap → UNI (UNIUSDT)
- Cosmos/ATOM → ATOM (ATOMUSDT)
- NEAR → NEAR (NEARUSDT)
- Aptos → APT (APTUSDT)
- Arbitrum → ARB (ARBUSDT)
- Optimism → OP (OPUSDT)
- SUI → SUI (SUIUSDT)
- PEPE → PEPE (PEPEUSDT)

**价格方向判断规则**：
- 看涨关键词：reach, hit, break, above, 突破, 达到, 涨到, 超过 → direction = "above"
- 看跌关键词：drop, fall, below, under, 跌破, 跌到, 低于 → direction = "below"
- 默认（无明确方向）→ direction = "above"

**注意**：
- target_price 应为纯数字，$150k = 150000，$1m = 1000000
- binance_symbol 统一加 USDT 后缀

**输出格式**（严格JSON）：
{
    "symbol": "BTC",
    "binance_symbol": "BTCUSDT",
    "target_price": 150000,
    "direction": "above",
    "time_condition": "by December 31, 2026"
}

如果无法识别加密货币，返回：
{
    "symbol": null,
    "binance_symbol": null,
    "target_price": null,
    "direction": null,
    "time_condition": null,
    "error": "无法识别加密货币"
}

只输出JSON，不要任何解释。"""

    user_prompt = f"请解析以下问题：\n{question}"

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "qwen-turbo",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.1
                }
            )
            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()

            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])

            return json.loads(content)

    except Exception as e:
        return {
            "symbol": None,
            "binance_symbol": None,
            "target_price": None,
            "direction": None,
            "time_condition": None,
            "error": f"LLM解析失败: {str(e)}"
        }


def main(question: Any) -> tuple:
    if isinstance(question, dict):
        question = question.get("content", question.get("question", str(question)))
    question = str(question).strip()

    if not question:
        error_result = {
            "symbol": None,
            "binance_symbol": None,
            "target_price": None,
            "direction": None,
            "time_condition": None,
            "error": "问题为空"
        }
        return json.dumps(error_result, ensure_ascii=False), ""

    parsed = _llm_parse_question(question)
    binance_symbol = parsed.get("binance_symbol") or ""

    return json.dumps(parsed, ensure_ascii=False, indent=2), binance_symbol


def run_node(node):
    Outputs.clear()
    for i in range(len(node['Outputs'])):
        Outputs.append(node['Outputs'][i])

    question = ""
    if node.get('Inputs') and len(node['Inputs']) > 0:
        question = node['Inputs'][0].get('Context', '') or ''

    parsed_json, binance_symbol = main(question)

    if len(Outputs) > 0:
        Outputs[0]['Context'] = parsed_json
    if len(Outputs) > 1:
        Outputs[1]['Context'] = binance_symbol

    return Outputs
