import json
from datetime import datetime, timezone
from typing import Dict, Optional

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
    "组件功能\n"
    "量化分析报告生成节点：将K线数据和技术指标转换为自然语言报告，"
    "供下游LLM判定员作为概率评估的量化依据。\n\n"
    "参数\n```yaml\n"
    "inputs:\n"
    "  - name: KlineData\n    type: string\n    required: true\n    description: Crypto_Klines节点的输出JSON\n"
    "  - name: QuestionParsed\n    type: string\n    required: false\n    description: Crypto_ParseQuestion节点的输出JSON\n"
    "  - name: question\n    type: string\n    required: false\n    description: 原始问题（备用）\n"
    "outputs:\n"
    "  - name: QuantReport\n    type: string\n    description: 结构化的量化分析报告文本\n```"
)

def _parse_json_safe(text: str) -> Optional[Dict]:
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None

def _format_number(n, decimals: int = 2) -> str:
    if n is None:
        return "N/A"
    if abs(n) >= 1000000:
        return f"{n/1000000:.2f}M"
    if abs(n) >= 1000:
        return f"{n/1000:.2f}K"
    return f"{n:.{decimals}f}"

def _signal_to_chinese(signal: str) -> str:
    translations = {
        "STRONG_BULLISH": "强烈看涨", "BULLISH": "看涨", "NEUTRAL": "中性",
        "BEARISH": "看跌", "STRONG_BEARISH": "强烈看跌",
        "strong_bullish": "强烈看涨", "bullish": "看多排列", "neutral": "中性",
        "bearish": "看空排列", "strong_bearish": "强烈看跌",
        "overbought": "超买", "oversold": "超卖",
        "approaching_overbought": "接近超买", "approaching_oversold": "接近超卖",
        "golden_cross": "金叉", "death_cross": "死叉", "none": "无",
        "TRENDING_UP": "上升趋势", "TRENDING_DOWN": "下降趋势",
        "RANGING": "震荡", "VOLATILE": "高波动",
    }
    return translations.get(signal, signal)

def run_node(node):
    kline_json = node['Inputs'][0].get('Context') or ""
    question_parsed_json = node['Inputs'][1].get('Context') or ""

    kline_data = _parse_json_safe(kline_json)
    question_parsed = _parse_json_safe(question_parsed_json)

    if not kline_data or not kline_data.get("ok"):
        Outputs[0]['Context'] = "【量化分析报告】\n\n无法获取K线数据，技术分析不可用。\n"
        return Outputs

    symbol = kline_data.get("symbol", "UNKNOWN")
    interval = kline_data.get("interval", "1d")
    signals = kline_data.get("signals", {})
    indicators = kline_data.get("indicators", {})
    period_stats = kline_data.get("period_stats", {})
    current = kline_data.get("current", {})
    current_price = current.get("price")

    target_price = question_parsed.get("target_price") if question_parsed else None

    now_utc = datetime.now(timezone.utc)
    lines = []
    lines.append("=" * 50)
    lines.append(f"【{symbol} 量化技术分析报告】")
    lines.append(f"分析时间: {now_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    lines.append(f"数据周期: {interval}  |  K线数量: {kline_data.get('kline_count', 'N/A')}")
    lines.append("=" * 50)

    # 1. 价格概览
    lines.append("\n【价格概览】")
    lines.append(f"  当前价格: ${_format_number(current_price, 2)}")
    if period_stats:
        lines.append(f"  周期最高: ${_format_number(period_stats.get('high'), 2)}")
        lines.append(f"  周期最低: ${_format_number(period_stats.get('low'), 2)}")
        lines.append(f"  周期涨跌: {period_stats.get('period_change_pct', 0):.2f}%")
        lines.append(f"  波动幅度: {period_stats.get('range_pct', 0):.2f}%")

    # 2. 目标价格分析
    if target_price and current_price:
        lines.append("\n【目标价格分析】")
        lines.append(f"  目标价格: ${_format_number(target_price, 2)}")
        distance_pct = (target_price - current_price) / current_price * 100
        lines.append(f"  距离目标: {distance_pct:+.2f}%")
        if distance_pct > 50:
            lines.append(f"  难度评估: 需要上涨超过50%，难度极高")
        elif distance_pct > 20:
            lines.append(f"  难度评估: 需要上涨超过20%，难度较高")
        elif distance_pct > 0:
            lines.append(f"  难度评估: 目标高于当前价格，需要上涨趋势配合")
        elif distance_pct > -10:
            lines.append(f"  难度评估: 目标接近当前价格，可能性较大")
        else:
            lines.append(f"  难度评估: 目标低于当前价格较多，需要下跌趋势")

    # 3. 市场状态
    market_regime = signals.get("market_regime", {})
    if market_regime:
        lines.append("\n【市场状态】")
        regime = market_regime.get("regime", "UNKNOWN")
        regime_confidence = market_regime.get("confidence", 0)
        lines.append(f"  状态: {_signal_to_chinese(regime)} (置信度: {regime_confidence:.2f})")
        characteristics = market_regime.get("characteristics", {})
        if characteristics:
            lines.append(f"  趋势强度(ADX): {characteristics.get('trend_strength', 0):.1f}")
            lines.append(f"  波动率水平: {characteristics.get('volatility_level', 0):.2f}x")

    # 4. 核心技术指标
    lines.append("\n【技术指标】")
    details = signals.get("details", {})

    # EMA排列
    ema9 = indicators.get("ema9")
    ema21 = indicators.get("ema21")
    if ema9 is not None and ema21 is not None:
        trend_alignment = details.get("trend_alignment", "neutral")
        lines.append(f"  EMA排列: {_signal_to_chinese(trend_alignment)}")
        lines.append(f"    EMA9: ${_format_number(ema9, 2)}  EMA21: ${_format_number(ema21, 2)}")

    # MACD
    macd = indicators.get("macd")
    macd_signal = indicators.get("macd_signal")
    if macd is not None and macd_signal is not None:
        macd_status = "多头" if macd - macd_signal > 0 else "空头"
        lines.append(f"  MACD: {macd:.4f} (信号线: {macd_signal:.4f}) -> {macd_status}")
        macd_cross = details.get("macd_cross", "none")
        if macd_cross != "none":
            lines.append(f"    近期出现 {_signal_to_chinese(macd_cross)}")

    # RSI
    rsi = indicators.get("rsi")
    if rsi is not None:
        rsi_zone = details.get("rsi_zone", "neutral")
        lines.append(f"  RSI(14): {rsi:.2f} -> {_signal_to_chinese(rsi_zone)}")

    # ADX
    adx = indicators.get("adx")
    plus_di = indicators.get("plus_di")
    minus_di = indicators.get("minus_di")
    if adx is not None:
        lines.append(f"  ADX: {adx:.2f}")
        if plus_di is not None and minus_di is not None:
            di_trend = "多头" if plus_di > minus_di else "空头"
            lines.append(f"    +DI: {plus_di:.2f} | -DI: {minus_di:.2f} -> {di_trend}")

    # SMA
    sma50 = indicators.get("sma50")
    if sma50 is not None and current_price:
        deviation = ((current_price - sma50) / sma50 * 100) if sma50 > 0 else 0
        lines.append(f"  SMA50: ${_format_number(sma50, 2)} (偏离: {deviation:+.2f}%)")

    # ATR
    atr_val = indicators.get("atr")
    if atr_val is not None:
        lines.append(f"  ATR(14): {_format_number(atr_val, 4)}")

    # 5. 综合信号
    lines.append("\n【综合信号】")
    overall = signals.get("overall_signal", "NEUTRAL")
    signal_score = signals.get("signal_score", 0)
    confidence = signals.get("confidence", 0)
    direction = signals.get("direction", "neutral")

    lines.append(f"  综合判断: {_signal_to_chinese(overall)}")
    lines.append(f"  信号分数: {signal_score:.1f} / 100 ({direction})")
    lines.append(f"  置信度: {confidence:.2f}")

    scores = signals.get("scores", {})
    if scores:
        lines.append(f"  分类评分:")
        lines.append(f"    趋势: {scores.get('trend', 0):.1f}")
        lines.append(f"    动量: {scores.get('momentum', 0):.1f}")

    key_signals = signals.get("key_signals", [])
    if key_signals:
        lines.append(f"  关键信号:")
        for sig in key_signals[:5]:
            lines.append(f"    - {sig}")

    warnings = signals.get("warnings", [])
    if warnings:
        lines.append(f"  警告:")
        for warn in warnings[:3]:
            lines.append(f"    - {warn}")

    # 6. 量化概率建议
    lines.append("\n【量化参考建议】")

    base_prob = 0.50
    adjustments = []

    score_adj = (signal_score / 100) * 0.3
    adjustments.append((f"信号分数({signal_score:.1f})", score_adj))

    confidence_mult = confidence * 1.2
    adjustments = [(r, a * confidence_mult) for r, a in adjustments]

    if market_regime:
        r = market_regime.get("regime", "")
        if r in ("TRENDING_UP", "TRENDING_DOWN") and direction in ("bullish", "bearish"):
            adjustments.append(("趋势市场配合信号", +0.08))
        elif r == "VOLATILE":
            adjustments.append(("高波动市场风险", -0.05))

    if target_price and current_price:
        d = (target_price - current_price) / current_price * 100
        if d > 50:
            adjustments.append(("目标距离过远(>50%)", -0.20))
        elif d > 30:
            adjustments.append(("目标距离较远(30-50%)", -0.15))
        elif d > 20:
            adjustments.append(("目标距离中等(20-30%)", -0.10))
        elif d > 10:
            adjustments.append(("目标距离适中(10-20%)", -0.05))
        elif d > 0:
            adjustments.append(("目标接近(<10%)", +0.05))
        elif d > -10:
            adjustments.append(("已超过目标(0-10%)", +0.10))
        else:
            adjustments.append(("大幅超过目标(>10%)", +0.15))

    suggested_prob = base_prob
    for reason, adj in adjustments:
        suggested_prob += adj
        sign = "+" if adj > 0 else ""
        lines.append(f"  - {reason}: {sign}{adj*100:.0f}%")

    suggested_prob = max(0.05, min(0.95, suggested_prob))
    lines.append(f"\n  量化建议概率: {suggested_prob:.2f} ({suggested_prob*100:.0f}%)")
    lines.append(f"  （注：此为技术面参考，需结合基本面和消息面综合判断）")
    lines.append("\n" + "=" * 50)

    report = "\n".join(lines)
    Outputs[0]['Context'] = report
    return Outputs
