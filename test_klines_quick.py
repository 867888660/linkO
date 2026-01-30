#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
快速测试Crypto_Klines.py的新信号系统
"""
import sys
import json
sys.path.insert(0, 'Nodes')

from Crypto_Klines import run_node, Inputs, Outputs

# 构造测试节点
test_node = {
    'Inputs': [
        {'Context': 'BTCUSDT', 'name': 'Symbol'},  # BTC交易对
        {'Context': '1d', 'name': 'Interval'},      # 日线
        {'Num': 100, 'name': 'Limit'}               # 获取100根K线
    ],
    'Outputs': Outputs
}

print("=" * 60)
print("测试Crypto_Klines新信号系统")
print("=" * 60)
print(f"交易对: {test_node['Inputs'][0]['Context']}")
print(f"周期: {test_node['Inputs'][1]['Context']}")
print(f"K线数量: {test_node['Inputs'][2]['Num']}")
print()

try:
    # 运行节点
    print("正在获取K线数据并计算指标...")
    result = run_node(test_node)

    # 解析输出
    output_json = json.loads(result[0]['Context'])

    if output_json.get('ok'):
        print("✓ 数据获取成功")
        print()

        # 显示基本信息
        print(f"交易对: {output_json['symbol']}")
        print(f"K线数量: {output_json['kline_count']}")
        print(f"延迟: {output_json['latency_ms']}ms")
        print()

        # 显示当前价格
        current = output_json['current']
        print(f"当前价格: ${current['price']:,.2f}")
        print()

        # 显示新的技术指标
        indicators = output_json['indicators']
        print("--- 技术指标 ---")
        print(f"EMA(9/21/55): {indicators.get('ema9', 'N/A')} / {indicators.get('ema21', 'N/A')} / {indicators.get('ema55', 'N/A')}")
        print(f"RSI(14): {indicators.get('rsi', 'N/A')}")
        print(f"MACD: {indicators.get('macd', 'N/A')}")
        print(f"ADX: {indicators.get('adx', 'N/A')}")
        print(f"ATR: {indicators.get('atr', 'N/A')}")
        print(f"OBV: {indicators.get('obv', 'N/A')}")
        print()

        # 显示新的信号系统
        signals = output_json['signals']
        print("=" * 60)
        print("【新信号系统输出】")
        print("=" * 60)
        print(f"总体信号: {signals.get('overall_signal', 'N/A')}")
        print(f"方向: {signals.get('direction', 'N/A')}")
        print(f"信号分数: {signals.get('signal_score', 'N/A')} (-100 到 +100)")
        print(f"置信度: {signals.get('confidence', 'N/A')} (0-1)")
        print()

        # 显示分类评分
        scores = signals.get('scores', {})
        print("--- 分类评分 ---")
        print(f"趋势分数: {scores.get('trend', 'N/A')}")
        print(f"动量分数: {scores.get('momentum', 'N/A')}")
        print(f"成交量分数: {scores.get('volume', 'N/A')}")
        print(f"波动率分数: {scores.get('volatility', 'N/A')}")
        print(f"总分: {scores.get('overall', 'N/A')}")
        print()

        # 显示市场状态
        market_regime = signals.get('market_regime', {})
        print("--- 市场状态 ---")
        print(f"状态: {market_regime.get('regime', 'N/A')}")
        print(f"置信度: {market_regime.get('confidence', 'N/A')}")
        characteristics = market_regime.get('characteristics', {})
        print(f"趋势强度(ADX): {characteristics.get('trend_strength', 'N/A')}")
        print(f"波动率水平: {characteristics.get('volatility_level', 'N/A')}")
        print(f"成交量趋势: {characteristics.get('volume_profile', 'N/A')}")
        print()

        # 显示关键信号
        key_signals = signals.get('key_signals', [])
        if key_signals:
            print("--- 关键信号 ---")
            for i, sig in enumerate(key_signals, 1):
                print(f"{i}. {sig}")
            print()

        # 显示警告
        warnings = signals.get('warnings', [])
        if warnings:
            print("--- 警告 ---")
            for i, warn in enumerate(warnings, 1):
                print(f"{i}. {warn}")
            print()

        # 显示详细信息
        details = signals.get('details', {})
        print("--- 详细信息 ---")
        print(f"MACD交叉: {details.get('macd_cross', 'N/A')}")
        print(f"RSI区域: {details.get('rsi_zone', 'N/A')}")
        print(f"趋势排列: {details.get('trend_alignment', 'N/A')}")
        print(f"成交量状态: {details.get('volume_status', 'N/A')}")
        print(f"布林带位置: {details.get('bb_position', 'N/A')}")

        divergences = details.get('divergences', {})
        if any(divergences.values()):
            print(f"背离: RSI看多={divergences.get('rsi_bullish')}, RSI看空={divergences.get('rsi_bearish')}, MACD看多={divergences.get('macd_bullish')}, MACD看空={divergences.get('macd_bearish')}")

        print()
        print("=" * 60)
        print("✓ 测试成功！新信号系统运行正常")
        print("=" * 60)

    else:
        print(f"✗ 错误: {output_json.get('error')}")
        print(f"调试信息: {output_json.get('debug')}")

except Exception as e:
    print(f"✗ 测试失败: {e}")
    import traceback
    traceback.print_exc()
