"""
K线分析 - 工具函数模块（通用）
适用于加密货币和股票
"""
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def calculate_atr_avg(atr: List[Optional[float]], period: int = 20) -> float:
    """计算ATR平均值"""
    if not atr or len(atr) < period:
        return 0.0
    valid = [v for v in atr[-period:] if v is not None]
    return sum(valid) / len(valid) if valid else 0.0


def calculate_std_dev(data: List[float], mean: float) -> float:
    """计算标准差"""
    if not data:
        return 0.0
    variance = sum((x - mean) ** 2 for x in data) / len(data)
    return variance ** 0.5


def wilder_smooth(data: List[float], period: int) -> List[Optional[float]]:
    """Wilder平滑法（用于ADX/ATR计算）"""
    if len(data) < period:
        return [None] * len(data)
    result = [None] * len(data)
    result[period - 1] = sum(data[:period]) / period
    for i in range(period, len(data)):
        result[i] = (result[i - 1] * (period - 1) + data[i]) / period
    return result


def format_float(value: Optional[float], decimals: int = 2) -> Optional[float]:
    """格式化浮点数"""
    if value is None:
        return None
    return round(value, decimals)


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """安全除法（避免除零）"""
    if denominator == 0:
        return default
    return numerator / denominator
