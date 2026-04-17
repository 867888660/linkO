"""
加密货币K线分析节点 - 集中配置管理（v5 回测优化版）
v5 改进：
  - 10 symbol × 5 target × 500 bar 滚动回测
  - 三层优化：指标周期 → 特征权重 → 逻辑回归
  - 训练集 70% / 验证集 30% 划分
  - Brier score 验证集提升 4.1%, AUC 0.52→0.57
  - 校准误差 0.18→0.16
v5 信号分布: 7 features, ADX continuous interpolation
"""

# =========================
# 技术指标参数
# =========================
INDICATOR_CONFIG = {
    # v4: fast=14, slow=35, signal=9
    "macd": {"fast": 3, "slow": 34, "signal": 9},
    # v4: period=19
    "rsi": {"period": 5},
    # v4: periods=[4, 10]
    "ema": {"periods": [8, 24]},
    # v4: period=19
    "adx": {"period": 20},
    # v4: period=24
    "atr": {"period": 44},
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
# 7 个特征 × ADX 连续插值线性模型
# =========================
SIGNAL_CONFIG = {
    "feature_keys": [
        "adx_normalized", "atr_ratio", "bb_position",
        "macd_hist_delta", "roc_20", "roc_5", "rsi_normalized",
    ],

    # v3.1: bb_period=27
    "bb_period": 30,

    # 盘整模式权重 (ADX 低)
    # v4: adx=0.80, atr=-0.15, bb=-2.28, macd_hd=-0.79, roc20=1.07, roc5=0.76, rsi=-1.13
    "weights_ranging": {
        "adx_normalized":   2.0464,
        "atr_ratio":        1.7113,
        "bb_position":     -3.0929,
        "macd_hist_delta":  0.4231,
        "roc_20":          -0.1791,
        "roc_5":            1.1798,
        "rsi_normalized":   2.2464,
    },
    # 趋势模式权重 (ADX 高)
    # v4: adx=-0.26, atr=-0.90, bb=2.64, macd_hd=-2.00, roc20=2.49, roc5=-0.25, rsi=-1.71
    "weights_trending": {
        "adx_normalized":   0.3679,
        "atr_ratio":        0.1495,
        "bb_position":      2.3633,
        "macd_hist_delta":  0.0734,
        "roc_20":           2.3708,
        "roc_5":           -0.0523,
        "rsi_normalized":  -2.9195,
    },

    "regime": {
        "trend_thresholds": {"strong": 25, "weak": 20},
        "volatility_thresholds": {"high_atr": 1.5, "high_bb": 1.5},
        "sma_proximity": 0.03,
        "volume_trend": {"increasing": 1.5, "decreasing": 0.6},
        "confidence": {
            "strong_trend_base": 0.55, "strong_trend_slope": 0.009,
            "volatile": 0.4, "ranging_base": 0.7,
            "ranging_slope_divisor": 40, "weak_trend": 0.5,
            "sma_converged": 0.6, "fallback": 0.4
        }
    },
}
