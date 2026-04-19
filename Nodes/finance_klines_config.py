"""
股票K线分析节点 - 集中配置管理（v5 回测优化版）
v5 改进：
  - 10 symbol × 5 target × 500 bar 滚动回测
  - 三层优化：指标周期 → 特征权重 → 逻辑回归
  - 训练集 70% / 验证集 30% 划分
  - Brier score 验证集提升 37.4%, AUC 0.65→0.82
  - 校准误差 0.34→0.07
v5 信号分布: 6 features, ADX continuous interpolation
"""

# =========================
# 技术指标参数
# =========================
INDICATOR_CONFIG = {
    # v4: fast=5, slow=16, signal=9
    "macd": {"fast": 14, "slow": 19, "signal": 9},
    # v4: period=30
    "rsi": {"period": 41},
    # v4: periods=[13, 16]
    "ema": {"periods": [16, 18]},
    # v4: period=24
    "adx": {"period": 26},
    # v4: period=12
    "atr": {"period": 11},
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
# 6 个特征 × ADX 连续插值线性模型
# =========================
SIGNAL_CONFIG = {
    "feature_keys": [
        "adx_normalized", "atr_ratio", "bb_width",
        "macd_strength", "rsi2_normalized", "rsi_normalized",
    ],

    # v3.1: rsi2_period=10
    "rsi2_period": 12,
    # v3.1: bb_period=23
    "bb_period": 27,

    # 盘整模式权重 (ADX 低)
    # v4: adx=-0.74, atr=-0.05, bb=2.61, macd=-0.75, rsi2=1.84, rsi=-2.06
    "weights_ranging": {
        "adx_normalized": -3.4049,
        "atr_ratio":      -1.9170,
        "bb_width":        0.6061,
        "macd_strength":  -0.1927,
        "rsi2_normalized":  3.2823,
        "rsi_normalized":  -2.9815,
    },
    # 趋势模式权重 (ADX 高)
    # v4: adx=0.51, atr=0.18, bb=-0.28, macd=-0.94, rsi2=2.45, rsi=-2.19
    "weights_trending": {
        "adx_normalized":  0.0638,
        "atr_ratio":      -0.2337,
        "bb_width":       -1.7207,
        "macd_strength":   0.1628,
        "rsi2_normalized":  1.2759,
        "rsi_normalized":  -2.5327,
    },

    "regime": {
        "trend_thresholds": {"strong": 25, "weak": 20},
        "volatility_thresholds": {"high_atr": 1.5, "high_bb": 1.5},
        "sma_proximity": 0.02,
        "volume_trend": {"increasing": 1.3, "decreasing": 0.7},
        "confidence": {
            "strong_trend_base": 0.55, "strong_trend_slope": 0.009,
            "volatile": 0.4, "ranging_base": 0.7,
            "ranging_slope_divisor": 40, "weak_trend": 0.5,
            "sma_converged": 0.6, "fallback": 0.4
        }
    },
}
