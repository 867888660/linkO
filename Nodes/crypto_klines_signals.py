"""
加密货币K线分析节点 - 信号生成模块
精简版：趋势 + 动量两类信号，只保留强指向性指标
所有策略数值从 SIGNAL_CONFIG 读取，代码中无硬编码
"""
import logging
from typing import Dict, List

from crypto_klines_config import SIGNAL_CONFIG
from crypto_klines_utils import safe_divide, calculate_atr_avg

logger = logging.getLogger(__name__)


# =========================
# 趋势信号：EMA排列 + MACD位置/交叉 + ADX确认
# =========================
def _calc_trend_score(closes, ema9, ema21, DIF, DEA, histogram, adx) -> Dict:
    cfg = SIGNAL_CONFIG["trend_scores"]
    score = 0
    components = []
    price = closes[-1]

    # 1. EMA排列（40分）
    if ema9[-1] is not None and ema21[-1] is not None:
        if price > ema9[-1] > ema21[-1]:
            score += cfg["ema_alignment"]
            components.append(("EMA看多排列", cfg["ema_alignment"]))
        elif price < ema9[-1] < ema21[-1]:
            score -= cfg["ema_alignment"]
            components.append(("EMA看空排列", cfg["ema_alignment"]))

    # 2. MACD信号（40分）— 位置和金叉/死叉取较大者，不叠加
    macd_pts = 0
    macd_label = ""

    if DIF[-1] is not None and DEA[-1] is not None and histogram[-1] is not None:
        hist_abs = abs(histogram[-1])
        
        # 业界标准改进：历史回溯归一化 (Lookback Normalization)
        # 用当前的 MACD 柱子绝对值，除以近期（例如过去100根K线）的最大柱子绝对值。
        # 好处：1. 自动适应任何时间级别（1分/日线）；2. 自动适应当前品种的波动率；3. 跨零轴时分数正常，不暴走。
        recent_hists = [abs(h) for h in histogram[-100:] if h is not None]
        
        # 为了防止在极端死水行情中，微小的柱子也被当作"近期最大"从而给满分
        # 我们用当前的标的价格的极小比例（如 0.05%）作为一个基础底噪过滤（Noise Floor）
        noise_floor = price * 0.0005 
        max_hist_recent = max(max(recent_hists) if recent_hists else 0, noise_floor)
        
        strength = hist_abs / max_hist_recent
        # 限制上限为 1.0（虽然正常应该小于等于1，但防止浮点或计算溢出）
        strength = min(strength, 1.0)
        
        position_pts = cfg["macd_signal"] * strength
        if position_pts > macd_pts:
            macd_pts = position_pts
            macd_label = f"MACD{'看多' if DIF[-1] > DEA[-1] else '看空'}({strength:.1f})"

    if (DIF[-1] is not None and DEA[-1] is not None and
            DIF[-2] is not None and DEA[-2] is not None):
        prev = DIF[-2] - DEA[-2]
        curr = DIF[-1] - DEA[-1]
        cross_pts = cfg["macd_signal"]
        if prev < 0 < curr and cross_pts > macd_pts:
            macd_pts = cross_pts
            macd_label = "MACD金叉"
        elif prev > 0 > curr and cross_pts > macd_pts:
            macd_pts = cross_pts
            macd_label = "MACD死叉"

    if macd_pts > 0 and DIF[-1] is not None and DEA[-1] is not None:
        is_bullish = DIF[-1] > DEA[-1] or ("叉" in macd_label and "金" in macd_label)
        if is_bullish:
            score += macd_pts
        else:
            score -= macd_pts
        if macd_pts >= 10:
            components.append((macd_label, macd_pts))

    # 3. ADX确认（20分）
    if adx[-1] is not None and adx[-1] > 25:
        boost = cfg["adx_confirmation"] * min((adx[-1] - 25) / 25, 1.0)
        if score > 0:
            score += boost
        elif score < 0:
            score -= boost
        elif ema9[-1] is not None and ema21[-1] is not None:
            score += boost if ema9[-1] > ema21[-1] else -boost
        if boost >= 5:
            components.append((f"ADX确认({adx[-1]:.0f})", boost))

    return {"score": max(-100, min(100, score)), "components": components}


# =========================
# 动量信号：RSI超买超卖 + MACD柱状图加速
# =========================
def _calc_momentum_score(rsi, atr, regime_type) -> Dict:
    cfg = SIGNAL_CONFIG["momentum_scores"]
    thresholds = SIGNAL_CONFIG["rsi_thresholds"]
    atr_avg = calculate_atr_avg(atr)
    score = 0
    components = []
    rsi_zone = "neutral"

    # RSI阈值自适应
    if atr[-1] is not None and atr_avg > 0:
        atr_ratio = atr[-1] / atr_avg
    else:
        atr_ratio = 1.0

    if atr_ratio > thresholds["high_volatility"]["atr_ratio_min"]:
        upper = thresholds["high_volatility"]["upper"]
        lower = thresholds["high_volatility"]["lower"]
    elif atr_ratio < thresholds["low_volatility"]["atr_ratio_max"]:
        upper = thresholds["low_volatility"]["upper"]
        lower = thresholds["low_volatility"]["lower"]
    else:
        upper = thresholds["normal"]["upper"]
        lower = thresholds["normal"]["lower"]

    trend_discount = cfg["rsi_trend_discount"]
    zone_trigger = cfg["rsi_zone_trigger"]

    # RSI评分：统一用deviation连续计算，避免阈值边界跳变
    # deviation 0~0.4: 不触发
    # deviation 0.4~1.0: 偏离区，线性增长到 rsi_extreme 分
    # deviation > 1.0: 极值区（超买/超卖），固定 rsi_extreme 分
    if rsi[-1] is not None:
        is_ranging = regime_type in ("RANGING", "VOLATILE")
        midpoint = (upper + lower) / 2
        half_range = (upper - lower) / 2
        deviation = (rsi[-1] - midpoint) / half_range if half_range > 0 else 0

        max_pts = cfg["rsi_extreme"] if is_ranging else cfg["rsi_extreme"] * trend_discount

        if abs(deviation) > 1.0:
            # 超过阈值：满分
            pts = max_pts
            if deviation > 0:
                rsi_zone = "overbought"
                score -= pts
                components.append((f"RSI超买({rsi[-1]:.0f}>{upper})", pts))
            else:
                rsi_zone = "oversold"
                score += pts
                components.append((f"RSI超卖({rsi[-1]:.0f}<{lower})", pts))

        elif abs(deviation) > zone_trigger:
            # 偏离区：从0线性增长到max_pts
            # deviation=zone_trigger时pts=0，deviation=1.0时pts=max_pts
            ratio = (abs(deviation) - zone_trigger) / (1.0 - zone_trigger)
            pts = max_pts * ratio
            if deviation > 0:
                rsi_zone = "approaching_overbought"
                score -= pts
                if pts >= 8:
                    components.append((f"RSI偏高({rsi[-1]:.0f})", pts))
            else:
                rsi_zone = "approaching_oversold"
                score += pts
                if pts >= 8:
                    components.append((f"RSI偏低({rsi[-1]:.0f})", pts))

    return {"score": max(-100, min(100, score)), "components": components, "rsi_zone": rsi_zone}


# =========================
# 信号聚合
# =========================
def generate_signals(closes: List[float], DIF: List, DEA: List,
                     histogram: List, rsi: List, ema9: List, ema21: List,
                     adx: List, atr: List,
                     market_regime: Dict) -> Dict:
    """生成交易信号"""

    if len(closes) < 2:
        return {
            "overall_signal": "INSUFFICIENT_DATA",
            "signal_score": 0, "confidence": 0, "direction": "neutral",
            "scores": {"trend": 0, "momentum": 0, "overall": 0},
            "market_regime": market_regime,
            "key_signals": [], "warnings": [], "details": {}
        }

    regime_type = market_regime.get("regime", "RANGING")
    regime_confidence = market_regime.get("confidence", 0.5)
    agg = SIGNAL_CONFIG["aggregation"]

    # 计算两类信号
    trend = _calc_trend_score(closes, ema9, ema21, DIF, DEA, histogram, adx)
    momentum = _calc_momentum_score(rsi, atr, regime_type)

    # 加权总分
    weights = SIGNAL_CONFIG["regime_weights"].get(regime_type, SIGNAL_CONFIG["regime_weights"]["RANGING"])
    weighted = trend["score"] * weights["trend"] + momentum["score"] * weights["momentum"]
    total_w = weights["trend"] + weights["momentum"]
    base_score = safe_divide(weighted, total_w, 0.0)

    rcw = agg["regime_confidence_weight"]
    final_score = base_score * (1.0 - rcw + rcw * regime_confidence)

    # 置信度
    dir_th = agg["direction_threshold"]
    conf_levels = agg["confidence_levels"]
    trend_dir = 1 if trend["score"] > dir_th["trend"] else (-1 if trend["score"] < -dir_th["trend"] else 0)
    momentum_dir = 1 if momentum["score"] > dir_th["momentum"] else (-1 if momentum["score"] < -dir_th["momentum"] else 0)

    if trend_dir != 0 and trend_dir == momentum_dir:
        base_conf = conf_levels["strong_agreement"]
    elif trend_dir != 0 and momentum_dir == 0:
        base_conf = conf_levels["single_trend"]
    elif trend_dir == 0 and momentum_dir != 0:
        base_conf = conf_levels["single_momentum"]
    elif trend_dir != 0 and trend_dir != momentum_dir:
        base_conf = conf_levels["contradiction"]
    else:
        base_conf = conf_levels["no_signal"]

    confidence = base_conf * regime_confidence

    # 信号分类
    sig_th = SIGNAL_CONFIG["signal_thresholds"]
    if final_score > sig_th["strong_bullish"]["score"] and confidence > sig_th["strong_bullish"]["confidence"]:
        overall_signal, direction = "STRONG_BULLISH", "bullish"
    elif final_score > sig_th["bullish"]["score"]:
        overall_signal, direction = "BULLISH", "bullish"
    elif final_score < sig_th["strong_bearish"]["score"] and confidence > sig_th["strong_bearish"]["confidence"]:
        overall_signal, direction = "STRONG_BEARISH", "bearish"
    elif final_score < sig_th["bearish"]["score"]:
        overall_signal, direction = "BEARISH", "bearish"
    else:
        overall_signal, direction = "NEUTRAL", "neutral"

    # 关键信号
    all_comps = trend["components"] + momentum["components"]
    all_comps.sort(key=lambda x: x[1], reverse=True)
    key_signals = [c[0] for c in all_comps if c[1] >= 10][:5]

    # 警告
    warnings = []
    if regime_type == "VOLATILE":
        warnings.append(f"高波动市场（置信度{regime_confidence:.2f}）")
    atr_avg = calculate_atr_avg(atr)
    if atr[-1] is not None and atr_avg > 0 and atr[-1] / atr_avg > 1.5:
        warnings.append(f"ATR异常升高({atr[-1]/atr_avg:.1f}x)，注意风险")

    # MACD交叉
    macd_cross = "none"
    if (DIF[-1] is not None and DEA[-1] is not None and
            DIF[-2] is not None and DEA[-2] is not None):
        prev = DIF[-2] - DEA[-2]
        curr = DIF[-1] - DEA[-1]
        if prev < 0 < curr:
            macd_cross = "golden_cross"
        elif prev > 0 > curr:
            macd_cross = "death_cross"

    # EMA趋势排列
    if ema9[-1] is not None and ema21[-1] is not None:
        p = closes[-1]
        if p > ema9[-1] > ema21[-1]:
            trend_alignment = "bullish"
        elif p < ema9[-1] < ema21[-1]:
            trend_alignment = "bearish"
        else:
            trend_alignment = "neutral"
    else:
        trend_alignment = "insufficient_data"

    return {
        "overall_signal": overall_signal,
        "signal_score": round(final_score, 2),
        "confidence": round(confidence, 2),
        "direction": direction,
        "scores": {
            "trend": round(trend["score"], 1),
            "momentum": round(momentum["score"], 1),
            "overall": round(final_score, 1)
        },
        "market_regime": market_regime,
        "key_signals": key_signals,
        "warnings": warnings[:3],
        "details": {
            "macd_cross": macd_cross,
            "rsi_zone": momentum.get("rsi_zone", "neutral"),
            "trend_alignment": trend_alignment
        }
    }
