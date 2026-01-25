import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# =========================
# Node metadata
# =========================
OutPutNum = 1
InPutNum = 3

Outputs = [{
    "Num": None,
    "Kind": None,
    "Boolean": False,
    "Id": "Output1",
    "Context": None,
    "name": "QuantReport",
    "Link": 0,
    "Description": "量化分析报告，供LLM判定员参考"
} for _ in range(OutPutNum)]

Inputs = [
    {"Num": None, "Kind": "String", "Id": "Input1", "Context": None, "name": "KlineData", "Link": 0, "IsLabel": False, "Isnecessary": True},
    {"Num": None, "Kind": "String", "Id": "Input2", "Context": None, "name": "QuestionParsed", "Link": 0, "IsLabel": False, "Isnecessary": False},
    {"Num": None, "Kind": "String", "Id": "Input3", "Context": None, "name": "question", "Link": 0, "IsLabel": False, "Isnecessary": False},
]

NodeKind = "Normal"
Lable = [{"Id": "Label1", "Kind": "None"}]

for o in Outputs:
    o['Kind'] = 'String'

FunctionIntroduction = (
    "组件功能（简述代码整体功能）\n"
    "这是一个量化分析报告生成节点：将K线数据和技术指标转换为自然语言报告，"
    "供下游LLM判定员作为概率评估的量化依据。\n\n"
    "代码功能摘要（概括核心算法或主要处理步骤）\n"
    "1. 解析上游的K线数据和技术指标JSON\n"
    "2. 根据目标价格计算当前价格距离目标的百分比\n"
    "3. 综合技术指标生成多空信号强度评估\n"
    "4. 输出结构化的中文量化分析报告\n\n"
    "参数\n```yaml\n"
    "inputs:\n"
    "  - name: KlineData\n    type: string\n    required: true\n    description: Crypto_Klines节点的输出JSON\n"
    "  - name: QuestionParsed\n    type: string\n    required: false\n    description: Crypto_ParseQuestion节点的输出JSON\n"
    "  - name: question\n    type: string\n    required: false\n    description: 原始问题（备用）\n"
    "outputs:\n"
    "  - name: QuantReport\n    type: string\n    description: 结构化的量化分析报告文本\n```"
)

def _parse_json_safe(text: str) -> Optional[Dict]:
    """安全解析JSON"""
    if not text:
        return None
    try:
        return json.loads(text)
    except:
        return None

def _format_number(n: float, decimals: int = 2) -> str:
    """格式化数字"""
    if n is None:
        return "N/A"
    if abs(n) >= 1000000:
        return f"{n/1000000:.2f}M"
    if abs(n) >= 1000:
        return f"{n/1000:.2f}K"
    return f"{n:.{decimals}f}"

def _signal_to_chinese(signal: str) -> str:
    """信号翻译"""
    translations = {
        "strong_bullish": "强烈看涨",
        "bullish": "看涨",
        "neutral": "中性",
        "bearish": "看跌",
        "strong_bearish": "强烈看跌",
        "overbought": "超买",
        "oversold": "超卖",
        "golden_cross": "金叉",
        "death_cross": "死叉",
        "none": "无",
        "above_upper": "突破上轨",
        "below_lower": "跌破下轨",
        "within_bands": "带内运行",
    }
    return translations.get(signal, signal)

def run_node(node):
    kline_json = node['Inputs'][0].get('Context') or ""
    question_parsed_json = node['Inputs'][1].get('Context') or ""
    question = node['Inputs'][2].get('Context') or ""
    
    # 解析输入
    kline_data = _parse_json_safe(kline_json)
    question_parsed = _parse_json_safe(question_parsed_json)
    
    if not kline_data or not kline_data.get("ok"):
        report = "【量化分析报告】\n\n❌ 无法获取K线数据，技术分析不可用。\n"
        Outputs[0]['Context'] = report
        return Outputs
    
    # 提取数据
    symbol = kline_data.get("symbol", "UNKNOWN")
    interval = kline_data.get("interval", "1d")
    signals = kline_data.get("signals", {})
    indicators = kline_data.get("indicators", {})
    period_stats = kline_data.get("period_stats", {})
    current = kline_data.get("current", {})
    
    current_price = signals.get("current_price") or current.get("price")
    
    # 目标价格分析
    target_price = None
    if question_parsed:
        target_price = question_parsed.get("target_price")
    
    # 生成报告
    lines = []
    lines.append("=" * 50)
    lines.append(f"【{symbol} 量化技术分析报告】")
    lines.append(f"数据周期: {interval}  |  分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 50)
    
    # 1. 价格概览
    lines.append("\n📊 【价格概览】")
    lines.append(f"  当前价格: ${_format_number(current_price, 2)}")
    if period_stats:
        lines.append(f"  周期最高: ${_format_number(period_stats.get('high'), 2)}")
        lines.append(f"  周期最低: ${_format_number(period_stats.get('low'), 2)}")
        lines.append(f"  周期涨跌: {period_stats.get('period_change_pct', 0):.2f}%")
        lines.append(f"  波动幅度: {period_stats.get('range_pct', 0):.2f}%")
    
    # 2. 目标价格分析（如果有）
    if target_price and current_price:
        lines.append("\n🎯 【目标价格分析】")
        lines.append(f"  目标价格: ${_format_number(target_price, 2)}")
        distance_pct = (target_price - current_price) / current_price * 100
        lines.append(f"  距离目标: {distance_pct:+.2f}%")
        
        if distance_pct > 50:
            lines.append(f"  难度评估: ⚠️ 需要上涨超过50%，难度极高")
        elif distance_pct > 20:
            lines.append(f"  难度评估: ⚠️ 需要上涨超过20%，难度较高")
        elif distance_pct > 0:
            lines.append(f"  难度评估: 目标高于当前价格，需要上涨趋势配合")
        elif distance_pct > -10:
            lines.append(f"  难度评估: 目标接近当前价格，可能性较大")
        else:
            lines.append(f"  难度评估: 目标低于当前价格较多，需要下跌趋势")
    
    # 3. 技术指标
    lines.append("\n📈 【技术指标】")
    
    # MACD
    macd = indicators.get("macd")
    macd_signal = indicators.get("macd_signal")
    if macd is not None and macd_signal is not None:
        macd_diff = macd - macd_signal
        macd_status = "多头" if macd_diff > 0 else "空头"
        lines.append(f"  MACD: {macd:.4f} (信号线: {macd_signal:.4f}) → {macd_status}")
        if signals.get("macd_cross") and signals.get("macd_cross") != "none":
            lines.append(f"    ⚡ 近期出现 {_signal_to_chinese(signals.get('macd_cross'))}")
    
    # RSI
    rsi = indicators.get("rsi")
    if rsi is not None:
        rsi_status = _signal_to_chinese(signals.get("rsi_signal", "neutral"))
        lines.append(f"  RSI(14): {rsi:.2f} → {rsi_status}")
    
    # 均线
    sma20 = indicators.get("sma20")
    sma50 = indicators.get("sma50")
    if sma20 is not None:
        price_vs_sma20 = signals.get("price_vs_sma20", 0)
        lines.append(f"  SMA20: ${_format_number(sma20, 2)} (价格偏离: {price_vs_sma20:+.2f}%)")
    if sma50 is not None:
        price_vs_sma50 = signals.get("price_vs_sma50", 0)
        lines.append(f"  SMA50: ${_format_number(sma50, 2)} (价格偏离: {price_vs_sma50:+.2f}%)")
    
    # 趋势
    trend = signals.get("trend")
    if trend:
        lines.append(f"  趋势判断: {'📈 多头趋势 (SMA20>SMA50)' if trend == 'bullish' else '📉 空头趋势 (SMA20<SMA50)'}")
        if signals.get("ma_cross") and signals.get("ma_cross") != "none":
            lines.append(f"    ⚡ 近期出现均线 {_signal_to_chinese(signals.get('ma_cross'))}")
    
    # 布林带
    bb_upper = indicators.get("bb_upper")
    bb_lower = indicators.get("bb_lower")
    if bb_upper is not None and bb_lower is not None:
        bb_position = signals.get("bb_position", 0.5)
        bb_status = _signal_to_chinese(signals.get("bb_signal", "within_bands"))
        lines.append(f"  布林带: 上轨${_format_number(bb_upper, 2)} 下轨${_format_number(bb_lower, 2)}")
        lines.append(f"    位置: {bb_position:.0%} ({bb_status})")
    
    # 4. 综合信号
    lines.append("\n🔮 【综合信号】")
    bullish_count = signals.get("bullish_signals", 0)
    bearish_count = signals.get("bearish_signals", 0)
    overall = signals.get("overall_signal", "neutral")
    
    lines.append(f"  多头信号数: {bullish_count} | 空头信号数: {bearish_count}")
    lines.append(f"  综合判断: {_signal_to_chinese(overall)}")
    
    # 5. 量化概率建议
    lines.append("\n💡 【量化参考建议】")
    
    # 基于技术指标的概率调整建议
    base_prob = 0.50
    adjustments = []
    
    # MACD
    if signals.get("macd_trend") == "bullish":
        adjustments.append(("MACD多头", +0.05))
    elif signals.get("macd_trend") == "bearish":
        adjustments.append(("MACD空头", -0.05))
    
    if signals.get("macd_cross") == "golden_cross":
        adjustments.append(("MACD金叉", +0.08))
    elif signals.get("macd_cross") == "death_cross":
        adjustments.append(("MACD死叉", -0.08))
    
    # RSI
    if signals.get("rsi_signal") == "oversold":
        adjustments.append(("RSI超卖反弹预期", +0.05))
    elif signals.get("rsi_signal") == "overbought":
        adjustments.append(("RSI超买回调风险", -0.05))
    
    # 趋势
    if signals.get("trend") == "bullish":
        adjustments.append(("多头趋势", +0.05))
    elif signals.get("trend") == "bearish":
        adjustments.append(("空头趋势", -0.05))
    
    # 目标距离
    if target_price and current_price:
        distance_pct = (target_price - current_price) / current_price * 100
        if distance_pct > 50:
            adjustments.append(("目标距离过远(>50%)", -0.20))
        elif distance_pct > 30:
            adjustments.append(("目标距离较远(30-50%)", -0.15))
        elif distance_pct > 20:
            adjustments.append(("目标距离中等(20-30%)", -0.10))
        elif distance_pct > 10:
            adjustments.append(("目标距离适中(10-20%)", -0.05))
        elif distance_pct > 0:
            adjustments.append(("目标接近(<10%)", +0.05))
        elif distance_pct > -10:
            adjustments.append(("已超过目标(0-10%)", +0.10))
        else:
            adjustments.append(("大幅超过目标(>10%)", +0.15))
    
    # 计算建议概率
    suggested_prob = base_prob
    for reason, adj in adjustments:
        suggested_prob += adj
        sign = "+" if adj > 0 else ""
        lines.append(f"  • {reason}: {sign}{adj*100:.0f}%")
    
    suggested_prob = max(0.05, min(0.95, suggested_prob))
    
    lines.append(f"\n  📊 量化建议概率: {suggested_prob:.2f} ({suggested_prob*100:.0f}%)")
    lines.append(f"  （注：此为技术面参考，需结合基本面和消息面综合判断）")
    
    lines.append("\n" + "=" * 50)
    
    report = "\n".join(lines)
    Outputs[0]['Context'] = report
    return Outputs
