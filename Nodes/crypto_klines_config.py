"""
加密货币K线分析节点 - 集中配置管理（v3 特征选择+深度优化版）
训练集: 32 个加密货币 (BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT 等)
留出集: 8 个加密货币 (AXSUSDT, CHZUSDT, ENJUSDT, CRVUSDT 等)

优化日期: 2026-04-01
优化方法: Optuna 贝叶斯搜索 (TPE, 2000 trials, 12-worker 并行)
特征选择: 相关性去重 + 穷举组合实验 v3（356 个组合粗筛 + Top 15 精筛）
评估指标: Brier Score + Expected Edge + Calibration Slope 复合适应度
回测标的: 32 训练 + 8 留出 = 40 个加密货币
结果: 训练集 0.4191, 留出集 0.3344 (旧基线 0.1932, 提升 +73.1%)
新特征: 淘汰 ema_alignment/macd_strength/macd_cross，新增 bb_position/macd_hist_delta/roc_20/roc_5
"""

# =========================
# 技术指标参数
# =========================
INDICATOR_CONFIG = {
    "macd": {"fast": 14, "slow": 32, "signal": 11},
    "rsi": {"period": 20},
    "ema": {"periods": [5, 35]},
    "adx": {"period": 25},
    "atr": {"period": 12},
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
    # 使用的特征列表（v3: 淘汰 ema_alignment/macd_strength/macd_cross）
    "feature_keys": [
        "adx_normalized", "atr_ratio", "bb_position",
        "macd_hist_delta", "roc_20", "roc_5", "rsi_normalized",
    ],

    # 布林带周期
    "bb_period": 27,

    # 盘整模式权重 (ADX 低)
    "weights_ranging": {
        "adx_normalized": -2.8037,
        "atr_ratio":      -1.2321,
        "bb_position":     1.3268,
        "macd_hist_delta":  2.7606,
        "roc_20":         -2.6568,
        "roc_5":           2.7874,
        "rsi_normalized":   1.0606,
    },
    # 趋势模式权重 (ADX 高)
    "weights_trending": {
        "adx_normalized":  2.1817,
        "atr_ratio":      -0.8897,
        "bb_position":    -1.6545,
        "macd_hist_delta": -2.5849,
        "roc_20":         -2.1991,
        "roc_5":           1.0289,
        "rsi_normalized":  -1.5300,
    },

    # 市场状态检测参数（供 _detect_market_regime 使用）
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

# =========================
# 概率模型参数（逻辑回归）
# =========================
PROBABILITY_CONFIG = {
    "logit_bias":     -4.2000,
    "logit_score":    -1.4388,
    "logit_conf":      1.0500,
    "logit_dist":     -5.1205,
    "logit_interact":  1.0193,
}
