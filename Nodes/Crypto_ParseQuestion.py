import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

# =========================
# Node metadata
# =========================
OutPutNum = 1
InPutNum = 2

Outputs = [{
    "Num": None,
    "Kind": None,
    "Boolean": False,
    "Id": "Output1",
    "Context": None,
    "name": "Result",
    "Link": 0,
    "Description": "从question中提取的加密货币Symbol和目标价格"
} for _ in range(OutPutNum)]

Inputs = [
    {"Num": None, "Kind": "String", "Id": "Input1", "Context": None, "name": "question", "Link": 0, "IsLabel": False, "Isnecessary": True},
    {"Num": None, "Kind": "String", "Id": "Input2", "Context": None, "name": "keywords", "Link": 0, "IsLabel": False, "Isnecessary": False},
]

NodeKind = "Normal"
Lable = [{"Id": "Label1", "Kind": "None"}]

for o in Outputs:
    o['Kind'] = 'String'

FunctionIntroduction = (
    "组件功能（简述代码整体功能）\n"
    "这是一个加密货币问题解析节点：从自然语言问题中提取交易对Symbol和目标价格等关键信息，"
    "为下游的K线获取和技术分析节点提供输入。\n\n"
    "代码功能摘要（概括核心算法或主要处理步骤）\n"
    "1. 使用正则表达式从question中识别加密货币名称（BTC/ETH/SOL等）\n"
    "2. 提取目标价格（如 '突破10万'、'reach $50000' 等）\n"
    "3. 识别时间条件（如 '2月底'、'by March' 等）\n"
    "4. 自动转换为Binance交易对格式（如 BTCUSDT）\n\n"
    "参数\n```yaml\n"
    "inputs:\n"
    "  - name: question\n    type: string\n    required: true\n    description: 预测市场的问题描述\n"
    "  - name: keywords\n    type: string\n    required: false\n    description: 额外关键词（可选）\n"
    "outputs:\n"
    "  - name: Result\n    type: string\n    description: JSON字符串，包含解析出的symbol、target_price、direction等\n```"
)

# =========================
# Crypto Symbol Mapping
# =========================
CRYPTO_ALIASES = {
    # 主流币
    "BITCOIN": "BTC",
    "BTC": "BTC",
    "ETHEREUM": "ETH",
    "ETH": "ETH",
    "ETHER": "ETH",
    "SOLANA": "SOL",
    "SOL": "SOL",
    "RIPPLE": "XRP",
    "XRP": "XRP",
    "DOGECOIN": "DOGE",
    "DOGE": "DOGE",
    "CARDANO": "ADA",
    "ADA": "ADA",
    "AVALANCHE": "AVAX",
    "AVAX": "AVAX",
    "POLKADOT": "DOT",
    "DOT": "DOT",
    "CHAINLINK": "LINK",
    "LINK": "LINK",
    "POLYGON": "MATIC",
    "MATIC": "MATIC",
    "LITECOIN": "LTC",
    "LTC": "LTC",
    "BINANCE COIN": "BNB",
    "BNB": "BNB",
    "SHIBA": "SHIB",
    "SHIB": "SHIB",
    "TRON": "TRX",
    "TRX": "TRX",
    "UNISWAP": "UNI",
    "UNI": "UNI",
    "COSMOS": "ATOM",
    "ATOM": "ATOM",
    "NEAR": "NEAR",
    "APTOS": "APT",
    "APT": "APT",
    "ARBITRUM": "ARB",
    "ARB": "ARB",
    "OPTIMISM": "OP",
    "OP": "OP",
    "SUI": "SUI",
    "PEPE": "PEPE",
    "FLOKI": "FLOKI",
    "BONK": "BONK",
    # 稳定币（用于识别交易对）
    "USDT": "USDT",
    "USDC": "USDC",
    "BUSD": "BUSD",
}

def _extract_crypto_symbol(text: str) -> Optional[str]:
    """从文本中提取加密货币符号"""
    text_upper = text.upper()
    
    # 按长度排序，优先匹配长的（如 BITCOIN 优先于 BTC）
    sorted_aliases = sorted(CRYPTO_ALIASES.keys(), key=len, reverse=True)
    
    for alias in sorted_aliases:
        # 使用单词边界匹配
        pattern = r'\b' + re.escape(alias) + r'\b'
        if re.search(pattern, text_upper):
            return CRYPTO_ALIASES[alias]
    
    return None

def _extract_target_price(text: str) -> Optional[float]:
    """从文本中提取目标价格"""
    patterns = [
        # $120,000 or $120000 (带逗号或不带)
        r'\$\s*([\d]{1,3}(?:,\d{3})*(?:\.\d+)?)',
        r'\$\s*(\d+(?:\.\d+)?)',
        # 100,000 USD/USDT
        r'([\d]{1,3}(?:,\d{3})*)\s*(?:USD|USDT|美元)',
        r'(\d+)\s*(?:USD|USDT|美元)',
        # reach/hit/break $100000 or 100000
        r'(?:reach|hit|break|突破|达到|超过|涨到)\s*\$?\s*([\d]{1,3}(?:,\d{3})*(?:\.\d+)?)',
        r'(?:reach|hit|break|突破|达到|超过|涨到)\s*\$?\s*(\d+(?:\.\d+)?)',
        # 100000 目标
        r'([\d,]+(?:\.\d+)?)\s*(?:目标|target)',
        # 10万/12万 (中文数字)
        r'(\d+)\s*万',
        # above/below 100000
        r'(?:above|below|高于|低于)\s*\$?\s*([\d,]+(?:\.\d+)?)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            price_str = match.group(1).replace(',', '')
            try:
                price = float(price_str)
                # 处理中文"万"
                if '万' in text[match.start():match.end() + 5]:
                    price = price * 10000
                # 基本校验：加密货币价格通常不会小于0.0001或大于10M
                if price >= 0.0001 and price <= 10000000:
                    return price
            except:
                continue
    
    return None

def _extract_direction(text: str) -> str:
    """提取预测方向"""
    text_lower = text.lower()
    
    bullish_keywords = ['reach', 'hit', 'break', 'above', 'over', 'exceed', 
                        '突破', '达到', '超过', '涨到', '上涨', 'bullish', 'pump']
    bearish_keywords = ['fall', 'drop', 'below', 'under', 'crash',
                        '跌破', '下跌', '跌到', 'bearish', 'dump']
    
    for kw in bullish_keywords:
        if kw in text_lower:
            return "bullish"
    
    for kw in bearish_keywords:
        if kw in text_lower:
            return "bearish"
    
    return "unknown"

def _extract_time_condition(text: str) -> Optional[str]:
    """提取时间条件"""
    patterns = [
        # by March 2026
        r'by\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s*(\d{4})?',
        # 2月底/3月
        r'(\d{1,2})月(?:底|末|前|中)?',
        # end of Q1
        r'(?:end of\s+)?Q([1-4])',
        # 2026年
        r'(\d{4})年',
        # before/after date
        r'(?:before|after)\s+(\w+\s+\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)
    
    return None

def run_node(node):
    question = node['Inputs'][0].get('Context') or ""
    keywords = node['Inputs'][1].get('Context') or ""
    
    # 合并question和keywords
    full_text = f"{question} {keywords}".strip()
    
    if not full_text:
        result = {
            "ok": False,
            "error": "No question provided",
            "symbol": None,
            "binance_symbol": None,
        }
        Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False, indent=2)
        return Outputs
    
    # 提取信息
    crypto_symbol = _extract_crypto_symbol(full_text)
    target_price = _extract_target_price(full_text)
    direction = _extract_direction(full_text)
    time_condition = _extract_time_condition(full_text)
    
    # 构造Binance交易对
    binance_symbol = None
    if crypto_symbol and crypto_symbol not in ["USDT", "USDC", "BUSD"]:
        binance_symbol = f"{crypto_symbol}USDT"
    
    result = {
        "ok": True,
        "original_question": question,
        "symbol": crypto_symbol,
        "binance_symbol": binance_symbol,
        "target_price": target_price,
        "direction": direction,
        "time_condition": time_condition,
        "is_crypto_question": crypto_symbol is not None,
        "analysis_type": "price_prediction" if target_price else "general",
    }
    
    Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False, indent=2)
    return Outputs
