"""
股票K线分析节点 - 集中配置管理（v3 深度优化版）
训练集: 40 只美股 (AAPL, MSFT, NVDA, GOOGL, AMZN 等)
留出集: 10 只美股 (GS, C, WFC, DIS, NKE 等)

优化日期: 2026-03-31
优化方法: Optuna 贝叶斯搜索 (TPE, 2000 trials, 3-model 并行对比)
评估指标: Brier Score + Expected Edge + Calibration Slope 复合适应度
特征选择: 相关性去重 + 穷举组合实验 v3（307 个组合粗筛 + Top 15 精筛）
回测标的: 40 训练 + 10 留出 = 50 只美股
结果: 训练集 0.3251, 留出集 0.3303 (零过拟合, gap=-0.005)
新特征: 淘汰 ema_alignment/macd_cross，新增 bb_width/rsi2_normalized
"""

# =========================
# 技术指标参数
# =========================
INDICATOR_CONFIG = {
    "macd": {"fast": 9, "slow": 20, "signal": 12},
    "rsi": {"period": 17},
    "ema": {"periods": [14, 32]},
    "adx": {"period": 25},
    "atr": {"period": 10},
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
# 新特征组合: adx_normalized, atr_ratio, bb_width, macd_strength, rsi2_normalized, rsi_normalized
# =========================
SIGNAL_CONFIG = {
    # 使用的特征列表（v3: 替换 ema_alignment/macd_cross → bb_width/rsi2_normalized）
    "feature_keys": [
        "adx_normalized", "atr_ratio", "bb_width",
        "macd_strength", "rsi2_normalized", "rsi_normalized",
    ],

    # 短周期 RSI 的周期
    "rsi2_period": 10,

    # 布林带周期
    "bb_period": 23,

    # 盘整模式权重 (ADX 低)
    "weights_ranging": {
        "adx_normalized": -2.2781,
        "atr_ratio":      -2.6714,
        "bb_width":        1.1199,
        "macd_strength":  -1.0154,
        "rsi2_normalized":  2.0975,
        "rsi_normalized":  -0.9937,
    },
    # 趋势模式权重 (ADX 高)
    "weights_trending": {
        "adx_normalized": -2.0698,
        "atr_ratio":      -2.0449,
        "bb_width":       -0.6609,
        "macd_strength":   0.3328,
        "rsi2_normalized":  0.6753,
        "rsi_normalized":   0.9924,
    },

    # 市场状态检测参数（供 _detect_market_regime 使用）
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

# =========================
# 概率模型参数（逻辑回归）
# p = sigmoid(bias + score_w * signal + conf_w * confidence + dist_w * distance + interact_w * signal * confidence)
# =========================
PROBABILITY_CONFIG = {
    "logit_bias":     -4.6175,
    "logit_score":     4.4153,
    "logit_conf":     -3.1360,
    "logit_dist":     -4.3017,
    "logit_interact":  3.4576,
}
