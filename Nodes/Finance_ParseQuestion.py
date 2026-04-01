"""
Finance_ParseQuestion - 纯LLM解析股票相关问题
从自然语言问题中智能提取：股票代码、目标价格、方向、时间条件
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
    {'Num': None, 'Kind': 'String', 'Boolean': False, 'Id': 'Output2', 'Context': None, 'name': 'yfinance_symbol', 'Link': 0, 'Description': 'yfinance股票符号'}
]

Inputs = [
    {'Num': None, 'Kind': 'String', 'Id': 'Input1', 'Context': None, 'name': 'question', 'Link': 0, 'IsLabel': False, 'Isnecessary': True},
    {'Num': None, 'Kind': 'Trigger', 'Id': 'Input_Trigger_IsFinance', 'Context': None, 'name': 'IsFinance_Trigger', 'Link': 0, 'IsLabel': False, 'Isnecessary': False}
]

NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

FunctionIntroduction = (
    "组件功能\n"
    "股票问题解析节点：从自然语言问题中智能提取股票代码、目标价格、方向、时间条件。\n\n"
    "参数\n```yaml\n"
    "inputs:\n"
    "  - name: question\n    type: string\n    required: true\n    description: 用户问题，如'Apple股价能涨到300吗？'\n"
    "outputs:\n"
    "  - name: parsed_json\n    type: string\n    description: 解析结果JSON，包含symbol/target_price/direction等\n"
    "  - name: yfinance_symbol\n    type: string\n    description: yfinance股票符号，如AAPL\n```"
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

    system_prompt = """你是一个专业的股票市场问题解析助手。你需要从用户的问题中提取以下信息：

1. **symbol**: 股票代码（如 AAPL, TSLA, MSFT 等）
2. **yfinance_symbol**: yfinance格式的股票符号（美股直接用代码如 AAPL，港股如 9988.HK，日股如 7203.T）
3. **target_price**: 目标价格（数字，如果问题中没有具体价格则为 null）
4. **direction**: 价格方向（"above" 表示看涨/突破/达到，"below" 表示看跌/跌破）
5. **time_condition**: 时间条件描述（如 "by March 2026"，没有则为 null）

**常见公司名/别名到股票代码的映射**：
- 苹果/Apple → AAPL
- 特斯拉/Tesla → TSLA
- 微软/Microsoft → MSFT
- 英伟达/NVIDIA/黄仁勋 → NVDA
- 谷歌/Google/Alphabet → GOOGL
- 亚马逊/Amazon → AMZN
- Meta/脸书/Facebook → META
- 台积电/TSMC → TSM
- 阿里巴巴/Alibaba → BABA
- 腾讯/Tencent → 0700.HK
- Netflix/奈飞 → NFLX
- AMD/超微 → AMD
- 英特尔/Intel → INTC
- 波音/Boeing → BA
- 迪士尼/Disney → DIS
- 可口可乐/Coca-Cola → KO
- 摩根大通/JPMorgan → JPM
- 高盛/Goldman Sachs → GS
- 伯克希尔/Berkshire → BRK-B
- 沙特阿美/Saudi Aramco → 2222.SR

**ETF和指数映射**：
- 标普500/S&P 500 → ^GSPC (指数) 或 SPY (ETF)
- 纳斯达克/NASDAQ → ^IXIC (指数) 或 QQQ (ETF)
- 道琼斯/Dow Jones → ^DJI (指数) 或 DIA (ETF)
- 黄金/Gold → GLD
- 白银/Silver → SLV
- 原油/Oil → USO

**价格方向判断规则**：
- 看涨关键词：reach, hit, break, above, 突破, 达到, 涨到, 超过, 站上, 市值超过 → direction = "above"
- 看跌关键词：drop, fall, below, under, 跌破, 跌到, 低于 → direction = "below"
- 默认（无明确方向）→ direction = "above"

**输出格式**（严格JSON）：
{
    "symbol": "AAPL",
    "yfinance_symbol": "AAPL",
    "target_price": 300,
    "direction": "above",
    "time_condition": "by June 2026"
}

如果无法识别股票，返回：
{
    "symbol": null,
    "yfinance_symbol": null,
    "target_price": null,
    "direction": null,
    "time_condition": null,
    "error": "无法识别股票"
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
            "yfinance_symbol": None,
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
            "yfinance_symbol": None,
            "target_price": None,
            "direction": None,
            "time_condition": None,
            "error": "问题为空"
        }
        return json.dumps(error_result, ensure_ascii=False), ""

    parsed = _llm_parse_question(question)
    yfinance_symbol = parsed.get("yfinance_symbol") or ""

    return json.dumps(parsed, ensure_ascii=False, indent=2), yfinance_symbol


def run_node(node):
    Outputs.clear()
    for i in range(len(node['Outputs'])):
        Outputs.append(node['Outputs'][i])

    question = ""
    if node.get('Inputs') and len(node['Inputs']) > 0:
        question = node['Inputs'][0].get('Context', '') or ''

    parsed_json, yfinance_symbol = main(question)

    if len(Outputs) > 0:
        Outputs[0]['Context'] = parsed_json
    if len(Outputs) > 1:
        Outputs[1]['Context'] = yfinance_symbol

    return Outputs
