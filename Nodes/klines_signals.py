"""
K线分析 - 信号生成模块 v3（通用）
特征驱动：通过 signal_config 中的 feature_keys 定义使用哪些特征
权重经 Optuna 贝叶斯搜索回测优化
适用于加密货币和股票，通过 signal_config 参数区分
"""
import logging
from typing import Dict, List, Optional

from crypto_klines_config import SIGNAL_CONFIG as _DEFAULT_SIGNAL_CONFIG
from klines_utils import safe_divide, calculate_atr_avg

logger = logging.getLogger(__name__)

# 默认特征列表（向后兼容 Crypto）
_DEFAULT_FEATURE_KEYS = ["ema_alignment", "macd_strength", "macd_cross",
                         "rsi_normalized", "adx_normalized", "atr_ratio"]

_LABEL_MAP = {
    "ema_alignment": "EMA排列", "macd_strength": "MACD强度",
    "macd_cross": "MACD交叉", "rsi_normalized": "RSI",
    "adx_normalized": "ADX", "atr_ratio": "ATR波动",
    "bb_width": "布林带宽度", "rsi2_normalized": "短周期RSI",
    "roc_5": "5日动量", "roc_20": "20日动量",
    "volume_ratio": "成交量变化", "bb_position": "布林带位置",
    "di_diff": "DI方向差", "price_vs_sma50": "价格偏离SMA50",
    "macd_hist_delta": "MACD柱变化",
}


# =========================
# 特征提取
# =========================
def _extract_features(closes, ema9, ema21, DIF, DEA, histogram, rsi, adx, atr,
                      extra_data=None):
    """提取所有可用特征，返回 dict。"""
    price = closes[-1]
    extra = extra_data or {}
    f = {}

    # EMA 排列
    if ema9[-1] is not None and ema21[-1] is not None:
        if price > ema9[-1] > ema21[-1]:
            f["ema_alignment"] = 1.0
        elif price < ema9[-1] < ema21[-1]:
            f["ema_alignment"] = -1.0
        else:
            f["ema_alignment"] = 0.0
    else:
        f["ema_alignment"] = 0.0

    # MACD 强度
    if DIF[-1] is not None and DEA[-1] is not None:
        diff = DIF[-1] - DEA[-1]
        recent_hists = [abs(h) for h in histogram[-100:] if h is not None]
        max_hist = max(max(recent_hists) if recent_hists else 1.0, price * 0.001)
        f["macd_strength"] = max(-1.0, min(1.0, diff / max_hist))
    else:
        f["macd_strength"] = 0.0

    # MACD 交叉
    f["macd_cross"] = 0.0
    if (DIF[-1] is not None and DEA[-1] is not None
            and DIF[-2] is not None and DEA[-2] is not None):
        prev_diff = DIF[-2] - DEA[-2]
        curr_diff = DIF[-1] - DEA[-1]
        if prev_diff < 0 < curr_diff:
            f["macd_cross"] = 1.0
        elif prev_diff > 0 > curr_diff:
            f["macd_cross"] = -1.0

    # RSI 标准化
    f["rsi_normalized"] = (rsi[-1] - 50.0) / 50.0 if rsi[-1] is not None else 0.0

    # ADX 标准化
    f["adx_normalized"] = adx[-1] / 50.0 if adx[-1] is not None else 0.0

    # ATR 比率
    atr_avg = calculate_atr_avg(atr, 20)
    f["atr_ratio"] = safe_divide(atr[-1], atr_avg, 1.0) if atr[-1] is not None else 1.0

    # 布林带宽度
    bb_upper = extra.get("bb_upper")
    bb_lower = extra.get("bb_lower")
    bb_mid = extra.get("bb_mid")
    if bb_upper is not None and bb_lower is not None and bb_mid is not None and bb_mid > 0:
        f["bb_width"] = (bb_upper - bb_lower) / bb_mid
    else:
        f["bb_width"] = 0.0

    # 布林带位置
    if bb_upper is not None and bb_lower is not None:
        bw = bb_upper - bb_lower
        f["bb_position"] = (price - bb_lower) / bw - 0.5 if bw > 0 else 0.0
    else:
        f["bb_position"] = 0.0

    # 短周期 RSI
    rsi2 = extra.get("rsi2")
    f["rsi2_normalized"] = (rsi2 - 50.0) / 50.0 if rsi2 is not None else f["rsi_normalized"]

    # DI 差
    plus_di = extra.get("plus_di")
    minus_di = extra.get("minus_di")
    if plus_di is not None and minus_di is not None:
        f["di_diff"] = (plus_di - minus_di) / 50.0
    else:
        f["di_diff"] = 0.0

    # 价格 vs SMA50
    sma50 = extra.get("sma50")
    if sma50 is not None and sma50 > 0:
        f["price_vs_sma50"] = (price - sma50) / sma50
    else:
        f["price_vs_sma50"] = 0.0

    # ROC 5 / ROC 20
    f["roc_5"] = (price - closes[-6]) / closes[-6] if len(closes) >= 6 else 0.0
    f["roc_20"] = (price - closes[-21]) / closes[-21] if len(closes) >= 21 else 0.0

    # 成交量变化
    volumes = extra.get("volumes")
    if volumes is not None and len(volumes) >= 20:
        vol_5 = sum(volumes[-5:]) / 5
        vol_20 = sum(volumes[-20:]) / 20
        f["volume_ratio"] = safe_divide(vol_5, vol_20, 1.0) - 1.0
    else:
        f["volume_ratio"] = 0.0

    # MACD 柱状图变化
    if (len(histogram) >= 2 and histogram[-1] is not None and histogram[-2] is not None):
        recent = [abs(h) for h in histogram[-50:] if h is not None]
        mx = max(max(recent) if recent else 1.0, price * 0.001)
        f["macd_hist_delta"] = max(-1.0, min(1.0, (histogram[-1] - histogram[-2]) / mx))
    else:
        f["macd_hist_delta"] = 0.0

    return f


# =========================
# 线性信号模型（ADX 连续插值）
# =========================
def _compute_signal_score(features_dict, adx_raw, signal_config):
    """用 ADX 连续插值 ranging ↔ trending 权重，计算信号分数。"""
    w_ranging = signal_config["weights_ranging"]
    w_trending = signal_config["weights_trending"]

    feat_keys = signal_config.get("feature_keys", _DEFAULT_FEATURE_KEYS)

    trend_strength = min(adx_raw / 50.0, 1.0) if adx_raw is not None else 0.5

    score = 0.0
    components = []
    for key in feat_keys:
        val = features_dict.get(key, 0.0)
        wr = w_ranging.get(key, 0.0)
        wt = w_trending.get(key, 0.0)
        w = wr * (1.0 - trend_strength) + wt * trend_strength
        contribution = w * val
        score += contribution
        if abs(contribution) >= 0.15:
            label = _LABEL_MAP.get(key, key)
            direction = "看多" if contribution > 0 else "看空"
            components.append((f"{label}{direction}", abs(contribution)))

    confidence = min(abs(score) / 3.0, 1.0)
    return score, confidence, components


# =========================
# 信号聚合
# =========================
def generate_signals(closes: List[float], DIF: List, DEA: List,
                     histogram: List, rsi: List, ema9: List, ema21: List,
                     adx: List, atr: List,
                     market_regime: Dict, signal_config=None,
                     extra_data: Optional[Dict] = None) -> Dict:
    """生成交易信号。extra_data 传入额外指标（布林带、短周期RSI等）。"""

    if len(closes) < 2:
        return {
            "overall_signal": "INSUFFICIENT_DATA",
            "signal_score": 0, "confidence": 0, "direction": "neutral",
            "scores": {"trend": 0, "momentum": 0, "overall": 0},
            "market_regime": market_regime,
            "key_signals": [], "warnings": [], "details": {}
        }

    _sc = signal_config or _DEFAULT_SIGNAL_CONFIG

    # 特征提取 + 线性模型
    features_dict = _extract_features(closes, ema9, ema21, DIF, DEA, histogram,
                                      rsi, adx, atr, extra_data=extra_data)
    adx_raw = adx[-1] if adx[-1] is not None else 0.0
    final_score, confidence, components = _compute_signal_score(features_dict, adx_raw, _sc)

    # 信号分类
    if final_score > 1.0 and confidence > 0.5:
        overall_signal, direction = "STRONG_BULLISH", "bullish"
    elif final_score > 0.4:
        overall_signal, direction = "BULLISH", "bullish"
    elif final_score < -1.0 and confidence > 0.5:
        overall_signal, direction = "STRONG_BEARISH", "bearish"
    elif final_score < -0.4:
        overall_signal, direction = "BEARISH", "bearish"
    else:
        overall_signal, direction = "NEUTRAL", "neutral"

    # 映射到 [-100, 100] 范围（兼容下游报告展示）
    score_100 = max(-100, min(100, final_score * 33.0))

    components.sort(key=lambda x: x[1], reverse=True)
    key_signals = [c[0] for c in components[:5]]

    # 辅助信息
    warnings = []
    regime_type = market_regime.get("regime", "RANGING")
    regime_confidence = market_regime.get("confidence", 0.5)
    if regime_type == "VOLATILE":
        warnings.append(f"高波动市场（置信度{regime_confidence:.2f}）")
    atr_avg = calculate_atr_avg(atr)
    if atr[-1] is not None and atr_avg > 0 and atr[-1] / atr_avg > 1.5:
        warnings.append(f"ATR异常升高({atr[-1]/atr_avg:.1f}x)，注意风险")

    macd_cross_detail = "none"
    if (DIF[-1] is not None and DEA[-1] is not None and
            DIF[-2] is not None and DEA[-2] is not None):
        prev = DIF[-2] - DEA[-2]
        curr = DIF[-1] - DEA[-1]
        if prev < 0 < curr:
            macd_cross_detail = "golden_cross"
        elif prev > 0 > curr:
            macd_cross_detail = "death_cross"

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

    rsi_zone = "neutral"
    if rsi[-1] is not None:
        if rsi[-1] > 70:
            rsi_zone = "overbought"
        elif rsi[-1] > 60:
            rsi_zone = "approaching_overbought"
        elif rsi[-1] < 30:
            rsi_zone = "oversold"
        elif rsi[-1] < 40:
            rsi_zone = "approaching_oversold"

    return {
        "overall_signal": overall_signal,
        "signal_score": round(score_100, 2),
        "confidence": round(confidence, 2),
        "direction": direction,
        "scores": {
            "trend": round(score_100 * 0.6, 1),
            "momentum": round(score_100 * 0.4, 1),
            "overall": round(score_100, 1)
        },
        "market_regime": market_regime,
        "key_signals": key_signals,
        "warnings": warnings[:3],
        "details": {
            "macd_cross": macd_cross_detail,
            "rsi_zone": rsi_zone,
            "trend_alignment": trend_alignment
        }
    }
