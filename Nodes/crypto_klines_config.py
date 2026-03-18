"""
加密货币K线分析节点 - 集中配置管理
精简版：只保留强趋势性指标（EMA/MACD/RSI/ADX/ATR）
所有策略相关数值集中于此，代码中不出现策略硬编码
"""

# =========================
# 技术指标参数
# =========================
INDICATOR_CONFIG = {
    "macd": {"fast": 8, "slow": 17, "signal": 7},
    "rsi": {"period": 14},
    "ema": {"periods": [9, 21]},
    "sma": {"periods": [50]},
    "bollinger": {"period": 20, "std_dev": 2.0},
    "adx": {"period": 14},
    "atr": {"period": 14}
}

# =========================
# HTTP连接配置
# =========================
HTTP_CONFIG = {
    "retries": {
        "total": 3,
        "backoff_factor": 0.4,
        "status_forcelist": (429, 500, 502, 503, 504)
    },
    "timeout": 15,
    "pool": {"connections": 20, "maxsize": 20}
}

# =========================
# 信号系统配置
# =========================
SIGNAL_CONFIG = {
    # RSI自适应阈值
    "rsi_thresholds": {
        "high_volatility": {"upper": 80, "lower": 20, "atr_ratio_min": 1.5},
        "normal":          {"upper": 70, "lower": 30},
        "low_volatility":  {"upper": 65, "lower": 35, "atr_ratio_max": 0.7}
    },

    # 市场状态识别
    "regime": {
        "trend_thresholds": {"strong": 25, "weak": 20},
        "volatility_thresholds": {"high_atr": 1.5, "high_bb": 1.5},
        "sma_proximity": 0.03,
        "volume_trend": {"increasing": 1.5, "decreasing": 0.6},
        "confidence": {
            "strong_trend_base": 0.55,
            "strong_trend_slope": 0.009,  # 每ADX点增加的置信度
            "volatile": 0.4,
            "ranging_base": 0.7,
            "ranging_slope_divisor": 40,  # (20 - adx) / divisor
            "weak_trend": 0.5,
            "sma_converged": 0.6,
            "fallback": 0.4
        }
    },

    # 两类信号的权重
    "regime_weights": {
        "TRENDING_UP":       {"trend": 1.6, "momentum": 0.8},
        "TRENDING_DOWN":     {"trend": 1.6, "momentum": 0.8},
        "RANGING":           {"trend": 0.6, "momentum": 1.5},
        "VOLATILE":          {"trend": 1.0, "momentum": 1.0},
        "INSUFFICIENT_DATA": {"trend": 1.0, "momentum": 1.0}
    },

    # 趋势信号分数分配（满分100）
    "trend_scores": {
        "ema_alignment": 40,
        "macd_signal": 40,
        "adx_confirmation": 20
    },

    # 动量信号分数分配
    "momentum_scores": {
        "rsi_extreme": 100,
        # 策略参数
        "rsi_trend_discount": 0.5,  # 趋势市场RSI打折系数
        "rsi_zone_trigger": 0.4    # RSI偏离中线触发阈值(0~1)
    },

    # 信号聚合参数
    "aggregation": {
        "regime_confidence_weight": 0.4,
        "direction_threshold": {"trend": 15, "momentum": 10},
        "confidence_levels": {
            "strong_agreement": 0.80,
            "single_trend": 0.60,
            "single_momentum": 0.45,
            "contradiction": 0.25,
            "no_signal": 0.35
        }
    },

    # 信号分类阈值
    "signal_thresholds": {
        "strong_bullish": {"score": 60, "confidence": 0.6},
        "bullish": {"score": 25, "confidence": 0.0},
        "strong_bearish": {"score": -60, "confidence": 0.6},
        "bearish": {"score": -25, "confidence": 0.0}
    }
}
