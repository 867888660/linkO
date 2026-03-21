"""
Crypto_ParseQuestion - 纯LLM解析加密货币问题
从自然语言问题中智能提取：交易对、目标价格、方向、时间条件
"""

import json
import os
import httpx
from pathlib import Path
from typing import Any

# ========== 节点基础信息 ==========
inputcount = 1
outputcount = 2
input_name = ["question"]
output_name = ["parsed_json", "binance_symbol"]

# 标准节点元数据（供工作流引擎识别）
OutPutNum = 2
InPutNum = 2  # 增加一个 Trigger 输入

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
    "组件功能（简述代码整体功能）\n"
    "这是一个纯LLM驱动的加密货币问题解析节点：从自然语言问题中智能提取交易对、目标价格、方向、时间条件。\n\n"
    "代码功能摘要（概括核心算法或主要处理步骤）\n"
    "1. 接收用户问题（支持中英文、俚语）\n"
    "2. 调用阿里云qwen-turbo模型进行智能解析\n"
    "3. 输出结构化JSON和Binance交易对符号\n\n"
    "参数\n```yaml\n"
    "inputs:\n"
    "  - name: question\n    type: string\n    required: true\n    description: 用户问题，如'BTC能涨到12万吗？'\n"
    "outputs:\n"
    "  - name: parsed_json\n    type: string\n    description: 解析结果JSON，包含symbol/target_price/direction等\n"
    "  - name: binance_symbol\n    type: string\n    description: Binance交易对，如BTCUSDT\n```"
)


def get_llm_api_key():
    """从环境变量读取当前组件的 API 密钥"""
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
    """使用LLM解析问题，提取加密货币交易信息"""
    
    api_key = get_llm_api_key()
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    
    system_prompt = """你是一个专业的加密货币问题解析助手。你需要从用户的问题中提取以下信息：

1. **symbol**: 加密货币符号（如 BTC, ETH, SOL 等）
2. **binance_symbol**: Binance 交易对格式（如 BTCUSDT, ETHUSDT）
3. **target_price**: 目标价格（数字，如果问题中没有具体价格则为 null）
4. **direction**: 价格方向（"above" 表示看涨/突破/达到，"below" 表示看跌/跌破）
5. **time_condition**: 时间条件描述（如 "by March 2026"，没有则为 null）

**常见加密货币别名映射**（你需要识别这些俚语/别名）：
- 大饼、比特、Bitcoin → BTC
- 以太、姨太、Ethereum → ETH
- 狗狗币、Doge、狗币 → DOGE
- 柴犬币、SHIB、二狗 → SHIB
- 瑞波、XRP → XRP
- 莱特、辣条 → LTC
- 波卡、DOT → DOT
- 艾达、ADA → ADA
- 索拉纳、SOL、索尔 → SOL
- 马蹄、MATIC、Polygon → MATIC
- 雪崩、AVAX → AVAX
- 链接、LINK → LINK
- 原子、ATOM → ATOM
- 近、NEAR → NEAR
- 沙盒、SAND → SAND
- PEPE、青蛙 → PEPE
- 香蕉枪、BANANA → BANANA

**价格方向判断规则**：
- 看涨关键词：reach, hit, break, above, 突破, 达到, 涨到, 超过, 站上 → direction = "above"
- 看跌关键词：drop, fall, below, under, 跌破, 跌到, 低于 → direction = "below"
- 默认（无明确方向）→ direction = "above"

**输出格式**（严格JSON）：
{
    "symbol": "BTC",
    "binance_symbol": "BTCUSDT",
    "target_price": 120000,
    "direction": "above",
    "time_condition": "by March 2026"
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
            
            # 清理可能的markdown代码块标记
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
    """
    主函数：解析加密货币问题
    
    Args:
        question: 用户问题（如 "Will BTC reach 120000 USD by March 2026?"）
        
    Returns:
        tuple: (parsed_json, binance_symbol)
    """
    # 处理输入
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
    
    # 调用LLM解析
    parsed = _llm_parse_question(question)
    
    # 提取binance_symbol
    binance_symbol = parsed.get("binance_symbol") or ""
    
    return json.dumps(parsed, ensure_ascii=False, indent=2), binance_symbol


def run_node(node):
    """
    工作流引擎调用入口
    从 node['Inputs'] 读取输入，调用 main()，结果写入 Outputs
    """
    # 清空并重建 Outputs
    Outputs.clear()
    for i in range(len(node['Outputs'])):
        Outputs.append(node['Outputs'][i])
    
    # 读取输入：question
    question = ""
    if node.get('Inputs') and len(node['Inputs']) > 0:
        question = node['Inputs'][0].get('Context', '') or ''
    
    # 调用 main 函数
    parsed_json, binance_symbol = main(question)
    
    # 写入输出
    if len(Outputs) > 0:
        Outputs[0]['Context'] = parsed_json
    if len(Outputs) > 1:
        Outputs[1]['Context'] = binance_symbol
    
    return Outputs


# ========== 测试代码 ==========
if __name__ == "__main__":
    test_questions = [
        "Will BTC reach 120000 USD by March 2026?",
        "大饼能涨到15万美元吗？",
        "以太坊会跌破2000吗？",
        "SOL price above 300 by end of year?",
        "狗狗币能到1美元吗",
        "PEPE会不会涨10倍？"
    ]
    
    for q in test_questions:
        print(f"\n问题: {q}")
        parsed_json, symbol = main(q)
        print(f"解析结果: {parsed_json}")
        print(f"交易对: {symbol}")
