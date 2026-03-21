import json
import logging
import os
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
    "name": "Result",
    "Link": 0,
    "Description": "K线数据JSON，包含OHLCV和技术指标"
} for _ in range(OutPutNum)]

Inputs = [
    {"Num": None, "Kind": "String", "Id": "Input1", "Context": None, "name": "Symbol", "Link": 0, "IsLabel": True, "Isnecessary": True},
    {"Num": None, "Kind": "String", "Id": "Input2", "Context": "1d", "name": "Interval", "Link": 0, "IsLabel": True, "Isnecessary": False},
    {"Num": None, "Kind": "Num", "Id": "Input3", "Context": None, "Num": 60, "name": "Limit", "Link": 0, "IsLabel": True, "Isnecessary": False},
]

NodeKind = "Normal"
Lable = [{"Id": "Label1", "Kind": "None"}]

for o in Outputs:
    o['Kind'] = 'String'

FunctionIntroduction = (
    "组件功能（简述代码整体功能）\n"
    "这是一个加密货币K线数据抓取与高级技术指标计算节点：从 Binance Spot REST API 获取历史K线数据，"
    "并计算多层次技术指标（MACD、RSI、EMA、ADX、ATR、OBV、布林带等），采用市场状态感知的加权信号系统，"
    "输出包含信号分数(-100到+100)、置信度评估、市场状态分类的完整量化分析JSON。\n\n"
    "代码功能摘要（概括核心算法或主要处理步骤）\n"
    "1. 调用 Binance /api/v3/klines 获取指定交易对的历史K线\n"
    "2. 计算技术指标：\n"
    "   - 趋势：MACD(8,17,6)、EMA(9,21,55)、SMA(20,50)、ADX(14)\n"
    "   - 动量：RSI(14，自适应阈值)、MACD柱状图\n"
    "   - 成交量：OBV、成交量趋势分析、价格-成交量背离检测\n"
    "   - 波动率：ATR(14)、布林带(20,2)\n"
    "3. 市场状态识别：TRENDING_UP/DOWN、RANGING、VOLATILE（含置信度评分）\n"
    "4. 加权信号生成：基于市场状态动态调整指标权重，计算四大类别评分（趋势/动量/成交量/波动率）\n"
    "5. 背离检测：RSI/MACD与价格的看多/看空背离模式\n"
    "6. 输出结构化JSON：包含signal_score、confidence、分类评分、关键信号、风险警告\n\n"
    "参数\n```yaml\n"
    "inputs:\n"
    "  - name: Symbol\n    type: string\n    required: true\n    description: 交易对，如 BTCUSDT、ETHUSDT\n"
    "  - name: Interval\n    type: string\n    required: false\n    default: 1d\n    description: K线周期，支持 1m/5m/15m/1h/4h/1d/1w\n"
    "  - name: Limit\n    type: number\n    required: false\n    default: 60\n    description: 获取K线数量（最多1000）\n"
    "outputs:\n"
    "  - name: Result\n    type: string\n    description: JSON字符串，包含K线数据、完整技术指标、加权信号系统输出（signal_score、confidence、市场状态、分类评分）\n```\n"
    "\n运行逻辑\n"
    "- 解析输入的交易对Symbol、周期Interval、数量Limit\n"
    "- 调用 Binance /api/v3/klines 获取OHLCV数据\n"
    "- 计算多层次技术指标：MACD(8,17,6)、RSI、EMA(9,21,55)、ADX、ATR、OBV、布林带、成交量分析\n"
    "- 检测市场状态（趋势/震荡/高波动）+ 置信度评估\n"
    "- 检测RSI/MACD背离模式\n"
    "- 生成加权量化信号：基于市场状态动态调整指标权重，输出-100到+100分数、0-1置信度、分类评分\n"
    "- 组装完整输出JSON（含indicators、signals、market_regime、key_signals、warnings）并返回"
)

# =========================
# HTTP session with retries
# =========================
def _make_session() -> requests.Session:
    s = requests.Session()
    total = int(os.getenv("HTTP_RETRIES", "3"))
    backoff = float(os.getenv("HTTP_BACKOFF", "0.4"))
    retry = Retry(
        total=total,
        connect=total,
        read=total,
        status=total,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

_SESS = _make_session()

# =========================
# Technical Indicators
# =========================
def _sma(data: List[float], period: int) -> List[Optional[float]]:
    """简单移动平均"""
    result = [None] * len(data)
    for i in range(period - 1, len(data)):
        result[i] = sum(data[i - period + 1:i + 1]) / period
    return result

def _ema(data: List[float], period: int) -> List[Optional[float]]:
    """指数移动平均"""
    result = [None] * len(data)
    if len(data) < period:
        return result
    
    # 第一个EMA用SMA初始化
    sma_first = sum(data[:period]) / period
    result[period - 1] = sma_first
    
    multiplier = 2 / (period + 1)
    for i in range(period, len(data)):
        result[i] = (data[i] - result[i - 1]) * multiplier + result[i - 1]
    
    return result

def _macd(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """MACD指标"""
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    
    DIF_line = [None] * len(closes)
    for i in range(len(closes)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            DIF_line[i] = ema_fast[i] - ema_slow[i]
    
    # 计算信号线（MACD的EMA）
    macd_values = [v for v in DIF_line if v is not None]
    DEA_line = [None] * len(closes)
    
    if len(macd_values) >= signal:
        start_idx = next(i for i, v in enumerate(DIF_line) if v is not None)
        ema_signal = _ema(macd_values, signal)
        for i, v in enumerate(ema_signal):
            if v is not None:
                DEA_line[start_idx + i] = v
    
    # 计算柱状图
    histogram = [None] * len(closes)
    for i in range(len(closes)):
        if DIF_line[i] is not None and DEA_line[i] is not None:
            histogram[i] = DIF_line[i] - DEA_line[i]
    
    return DIF_line, DEA_line, histogram

def _rsi(closes: List[float], period: int = 14) -> List[Optional[float]]:
    """RSI指标"""
    result = [None] * len(closes)
    if len(closes) < period + 1:
        return result
    
    gains = []
    losses = []
    
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(0, change))
        losses.append(max(0, -change))
    
    # 第一个RSI
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    if avg_loss == 0:
        result[period] = 100
    else:
        rs = avg_gain / avg_loss
        result[period] = 100 - (100 / (1 + rs))
    
    # 后续RSI（平滑）
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        if avg_loss == 0:
            result[i + 1] = 100
        else:
            rs = avg_gain / avg_loss
            result[i + 1] = 100 - (100 / (1 + rs))
    
    return result

def _bollinger_bands(closes: List[float], period: int = 20, std_dev: float = 2.0) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """布林带"""
    sma = _sma(closes, period)
    upper = [None] * len(closes)
    lower = [None] * len(closes)
    
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1:i + 1]
        std = (sum((x - sma[i]) ** 2 for x in window) / period) ** 0.5
        upper[i] = sma[i] + std_dev * std
        lower[i] = sma[i] - std_dev * std
    
    return upper, sma, lower

def _adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """
    ADX - 平均趋向指标（衡量趋势强度）
    返回: (adx, plus_di, minus_di)
    - ADX > 25: 强趋势
    - ADX < 20: 弱趋势/无趋势
    - +DI > -DI: 看多趋势
    - -DI > +DI: 看空趋势
    """
    if len(highs) < period + 1:
        return [None] * len(highs), [None] * len(highs), [None] * len(highs)

    # 计算真实波幅（TR）和方向性移动（DM）
    tr_list = []
    plus_dm_list = []
    minus_dm_list = []

    for i in range(1, len(closes)):
        # 真实波幅
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        tr_list.append(tr)

        # +DM: 当前高点 - 前一高点（正向移动）
        up_move = highs[i] - highs[i-1]
        # -DM: 前一低点 - 当前低点（负向移动）
        down_move = lows[i-1] - lows[i]

        plus_dm = up_move if up_move > down_move and up_move > 0 else 0
        minus_dm = down_move if down_move > up_move and down_move > 0 else 0

        plus_dm_list.append(plus_dm)
        minus_dm_list.append(minus_dm)

    # Wilder平滑法计算平滑TR、+DM、-DM
    def _wilder_smooth(data: List[float], period: int) -> List[float]:
        if len(data) < period:
            return [None] * len(data)

        result = [None] * len(data)
        # 第一个值用简单平均
        result[period-1] = sum(data[:period]) / period

        # 后续使用Wilder平滑：(前值 × (period-1) + 当前值) / period
        for i in range(period, len(data)):
            result[i] = (result[i-1] * (period - 1) + data[i]) / period

        return result

    smoothed_tr = _wilder_smooth(tr_list, period)
    smoothed_plus_dm = _wilder_smooth(plus_dm_list, period)
    smoothed_minus_dm = _wilder_smooth(minus_dm_list, period)

    # 计算+DI和-DI
    plus_di = [None] * len(closes)
    minus_di = [None] * len(closes)
    dx_list = []

    for i in range(len(smoothed_tr)):
        if smoothed_tr[i] is not None and smoothed_tr[i] > 0:
            plus_di[i+1] = 100 * smoothed_plus_dm[i] / smoothed_tr[i]
            minus_di[i+1] = 100 * smoothed_minus_dm[i] / smoothed_tr[i]

            # 计算DX
            di_sum = plus_di[i+1] + minus_di[i+1]
            if di_sum > 0:
                dx = 100 * abs(plus_di[i+1] - minus_di[i+1]) / di_sum
                dx_list.append(dx)
            else:
                dx_list.append(0)
        else:
            dx_list.append(None)

    # ADX是DX的平滑移动平均
    adx = [None] * len(closes)
    valid_dx = [x for x in dx_list if x is not None]

    if len(valid_dx) >= period:
        start_idx = next(i for i, v in enumerate(dx_list) if v is not None)
        # 第一个ADX用简单平均
        first_adx = sum(valid_dx[:period]) / period
        adx[start_idx + period] = first_adx

        # 后续ADX用Wilder平滑
        for i in range(start_idx + period + 1, len(closes)):
            dx_idx = i - 1  # dx_list比closes短1
            if dx_idx < len(dx_list) and dx_list[dx_idx] is not None:
                adx[i] = (adx[i-1] * (period - 1) + dx_list[dx_idx]) / period

    return adx, plus_di, minus_di


def _atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[Optional[float]]:
    """
    ATR - 平均真实波幅（衡量波动率）
    用途：止损设置、仓位管理、状态检测
    """
    if len(highs) < 2:
        return [None] * len(highs)

    # 计算真实波幅（TR）
    tr_list = [None]  # 第一根K线没有TR
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        tr_list.append(tr)

    # 计算ATR（Wilder平滑）
    atr = [None] * len(closes)

    if len(tr_list) >= period + 1:
        # 第一个ATR用简单平均
        atr[period] = sum(tr_list[1:period+1]) / period

        # 后续ATR用Wilder平滑：(前ATR × (period-1) + 当前TR) / period
        for i in range(period + 1, len(closes)):
            atr[i] = (atr[i-1] * (period - 1) + tr_list[i]) / period

    return atr


def _obv(closes: List[float], volumes: List[float]) -> List[float]:
    """
    OBV - 能量潮指标（追踪累计成交量流）
    OBV趋势 vs 价格趋势背离 = 潜在反转信号
    """
    if len(closes) != len(volumes) or len(closes) < 2:
        return [0] * len(closes)

    obv = [volumes[0]]  # 第一根K线OBV = 第一根K线成交量

    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            # 价格上涨，加上成交量
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i-1]:
            # 价格下跌，减去成交量
            obv.append(obv[-1] - volumes[i])
        else:
            # 价格不变，保持OBV
            obv.append(obv[-1])

    return obv


def _volume_analysis(volumes: List[float], closes: List[float], obv: List[float], period: int = 20) -> Dict:
    """
    增强成交量分析
    
    返回:
    - avg_volume: 周期平均成交量
    - volume_ratio: 当前成交量/平均成交量
    - volume_trend: 成交量趋势 (increasing/decreasing/stable)
    - price_volume_divergence: 价格-OBV背离 (none/bullish/bearish)
    """
    if len(volumes) < period:
        return {
            "avg_volume": 0,
            "volume_ratio": 1.0,
            "volume_trend": "insufficient_data",
            "price_volume_divergence": "none"
        }

    # 1. 平均成交量 & 成交量比率
    avg_volume = sum(volumes[-period:]) / period
    current_volume = volumes[-1]
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

    # 2. 成交量趋势（比较最近5根 vs 更早期的平均）
    recent_avg = sum(volumes[-5:]) / 5
    earlier_slice = volumes[-period:-5]
    earlier_avg = sum(earlier_slice) / len(earlier_slice) if earlier_slice else avg_volume

    if recent_avg > earlier_avg * 1.2:
        volume_trend = "increasing"
    elif recent_avg < earlier_avg * 0.8:
        volume_trend = "decreasing"
    else:
        volume_trend = "stable"

    # 3. 价格-OBV背离检测（使用首尾变化，统一计算方式）
    price_volume_divergence = "none"
    
    if len(closes) >= period and len(obv) >= period:
        # 价格变化率：(当前价格 - period前价格) / period前价格
        price_start = closes[-period]
        price_end = closes[-1]
        price_change_pct = (price_end - price_start) / price_start if price_start > 0 else 0

        # OBV净变化：当前OBV - period前OBV
        obv_change = obv[-1] - obv[-period]
        
        # OBV变化归一化：净流入量 / 总成交量 = 净流入比例
        # 这表示这段时间"看多方向"的成交量占比
        total_volume = sum(volumes[-period:])
        obv_change_ratio = obv_change / total_volume if total_volume > 0 else 0

        # 背离检测条件：
        # - 价格变化至少 2%（避免噪音）
        # - OBV净流入比例至少 10%（有明显的资金方向）
        # - 两者方向相反
        price_threshold = 0.02  # 2%
        obv_threshold = 0.10    # 10%

        if abs(price_change_pct) > price_threshold and abs(obv_change_ratio) > obv_threshold:
            # 价格上涨但OBV净流出（看跌背离）
            if price_change_pct > 0 and obv_change_ratio < 0:
                price_volume_divergence = "bearish"
            # 价格下跌但OBV净流入（看多背离）
            elif price_change_pct < 0 and obv_change_ratio > 0:
                price_volume_divergence = "bullish"

    return {
        "avg_volume": avg_volume,
        "volume_ratio": volume_ratio,
        "volume_trend": volume_trend,
        "price_volume_divergence": price_volume_divergence
    }


def _detect_divergences(closes: List[float], rsi: List[Optional[float]],
                       DIF_line: List[Optional[float]], window: int = 20) -> Dict:
    """
    检测多空背离
    - 看多背离：价格创新低，RSI/MACD创新高 → 反转信号
    - 看跌背离：价格创新高，RSI/MACD创新低 → 反转信号
    """
    divergences = {
        "rsi_bullish": False,
        "rsi_bearish": False,
        "macd_bullish": False,
        "macd_bearish": False,
        "divergence_strength": 0.0
    }

    if len(closes) < window + 5:
        return divergences

    # 辅助函数：找局部极值（简化版 - 寻找最近的高低点）
    def find_recent_extremes(data: List, lookback: int):
        """找到最近lookback周期内的局部高点和低点"""
        if len(data) < lookback:
            return None, None

        recent_data = data[-lookback:]
        high_idx = recent_data.index(max(recent_data))
        low_idx = recent_data.index(min(recent_data))

        # 转换为绝对索引
        high_idx = len(data) - lookback + high_idx
        low_idx = len(data) - lookback + low_idx

        return high_idx, low_idx

    # RSI背离检测
    if rsi[-1] is not None and None not in rsi[-window:]:
        valid_rsi = [v for v in rsi if v is not None]
        if len(valid_rsi) >= window:
            price_high_idx, price_low_idx = find_recent_extremes(closes, window)
            rsi_high_idx, rsi_low_idx = find_recent_extremes(rsi[-window:], window)

            if price_high_idx and rsi_high_idx:
                rsi_high_idx = len(rsi) - window + rsi_high_idx

                # 看跌背离：价格新高，RSI降低
                if price_high_idx > price_low_idx and rsi_high_idx < rsi_low_idx:
                    if closes[price_high_idx] > closes[price_low_idx] * 1.03:  # 至少3%价格变化
                        if rsi[price_high_idx] < rsi[price_low_idx]:
                            divergences["rsi_bearish"] = True
                            divergences["divergence_strength"] = 0.6

            if price_low_idx and rsi_low_idx:
                rsi_low_idx = len(rsi) - window + rsi_low_idx

                # 看多背离：价格新低，RSI升高
                if price_low_idx > price_high_idx and rsi_low_idx < rsi_high_idx:
                    if closes[price_low_idx] < closes[price_high_idx] * 0.97:  # 至少3%价格变化
                        if rsi[price_low_idx] > rsi[price_high_idx]:
                            divergences["rsi_bullish"] = True
                            divergences["divergence_strength"] = 0.6

    # MACD背离检测（类似逻辑）
    if DIF_line[-1] is not None and None not in DIF_line[-window:]:
        price_high_idx, price_low_idx = find_recent_extremes(closes, window)
        macd_high_idx, macd_low_idx = find_recent_extremes(DIF_line[-window:], window)

        if price_high_idx and macd_high_idx:
            macd_high_idx = len(DIF_line) - window + macd_high_idx

            if price_high_idx > price_low_idx and macd_high_idx < macd_low_idx:
                if closes[price_high_idx] > closes[price_low_idx] * 1.03:
                    if DIF_line[price_high_idx] < DIF_line[price_low_idx]:
                        divergences["macd_bearish"] = True
                        divergences["divergence_strength"] = max(divergences["divergence_strength"], 0.7)

        if price_low_idx and macd_low_idx:
            macd_low_idx = len(DIF_line) - window + macd_low_idx

            if price_low_idx > price_high_idx and macd_low_idx < macd_high_idx:
                if closes[price_low_idx] < closes[price_high_idx] * 0.97:
                    if DIF_line[price_low_idx] > DIF_line[price_high_idx]:
                        divergences["macd_bullish"] = True
                        divergences["divergence_strength"] = max(divergences["divergence_strength"], 0.7)

    return divergences

def _detect_market_regime(closes: List[float], highs: List[float], lows: List[float],
                         volumes: List[float], adx: List[Optional[float]],
                         atr: List[Optional[float]], bb_upper: List[Optional[float]],
                         bb_lower: List[Optional[float]], sma20: List[Optional[float]],
                         sma50: List[Optional[float]]) -> Dict:
    """
    市场状态分类 + 置信度评分

    状态类型：
    - TRENDING_UP（上升趋势）
    - TRENDING_DOWN（下降趋势）
    - RANGING（震荡）
    - VOLATILE（高波动）
    """
    if len(closes) < 50 or adx[-1] is None or atr[-1] is None:
        return {
            "regime": "INSUFFICIENT_DATA",
            "confidence": 0.0,
            "characteristics": {
                "trend_strength": 0,
                "volatility_level": 0,
                "volume_profile": "unknown"
            }
        }

    current_price = closes[-1]
    adx_value = adx[-1]

    # 计算ATR标准化（当前ATR / 20周期平均ATR）
    valid_atr = [v for v in atr[-20:] if v is not None]
    atr_avg = sum(valid_atr) / len(valid_atr) if valid_atr else 1.0
    atr_normalized = atr[-1] / atr_avg if atr_avg > 0 else 1.0

    # 计算BB宽度标准化
    if bb_upper[-1] and bb_lower[-1]:
        bb_width = bb_upper[-1] - bb_lower[-1]
        bb_widths = []
        for i in range(max(0, len(bb_upper) - 20), len(bb_upper)):
            if bb_upper[i] and bb_lower[i]:
                bb_widths.append(bb_upper[i] - bb_lower[i])
        bb_avg_width = sum(bb_widths) / len(bb_widths) if bb_widths else bb_width
        bb_width_normalized = bb_width / bb_avg_width if bb_avg_width > 0 else 1.0
    else:
        bb_width_normalized = 1.0

    # 成交量趋势
    if len(volumes) >= 20:
        recent_vol = sum(volumes[-5:]) / 5
        earlier_vol = sum(volumes[-20:-5]) / 15
        if recent_vol > earlier_vol * 1.2:
            volume_profile = "increasing"
        elif recent_vol < earlier_vol * 0.8:
            volume_profile = "decreasing"
        else:
            volume_profile = "stable"
    else:
        volume_profile = "unknown"

    # 状态分类逻辑
    regime = "RANGING"
    confidence = 0.5

    # 1. 强趋势检测（ADX > 25）
    if adx_value > 25:
        if sma20[-1] and sma50[-1]:
            if sma20[-1] > sma50[-1] and current_price > sma20[-1]:
                # 上升趋势
                regime = "TRENDING_UP"
                # 置信度随ADX增加而增加
                confidence = min(1.0, 0.6 + (adx_value - 25) / 50)
            elif sma20[-1] < sma50[-1] and current_price < sma20[-1]:
                # 下降趋势
                regime = "TRENDING_DOWN"
                confidence = min(1.0, 0.6 + (adx_value - 25) / 50)
            else:
                # ADX高但均线排列不清晰 - 可能是趋势转换
                regime = "VOLATILE"
                confidence = 0.5
        else:
            regime = "VOLATILE"
            confidence = 0.4

    # 2. 高波动检测（ATR或BB宽度显著扩大）
    elif atr_normalized > 1.5 or bb_width_normalized > 1.5:
        regime = "VOLATILE"
        confidence = min(1.0, max(atr_normalized, bb_width_normalized) / 2.0)

    # 3. 震荡市场（ADX < 20）
    elif adx_value < 20:
        regime = "RANGING"
        # ADX越低，震荡市场置信度越高
        confidence = min(1.0, 0.7 + (20 - adx_value) / 40)

    # 4. 中性区域（20 <= ADX <= 25）
    else:
        if sma20[-1] and sma50[-1]:
            if abs(sma20[-1] - sma50[-1]) / sma50[-1] < 0.02:
                # 均线非常接近
                regime = "RANGING"
                confidence = 0.6
            else:
                # 中等趋势
                if sma20[-1] > sma50[-1]:
                    regime = "TRENDING_UP"
                else:
                    regime = "TRENDING_DOWN"
                confidence = 0.5
        else:
            regime = "RANGING"
            confidence = 0.4

    return {
        "regime": regime,
        "confidence": round(confidence, 2),
        "characteristics": {
            "trend_strength": round(adx_value, 2),
            "volatility_level": round(atr_normalized, 2),
            "volume_profile": volume_profile
        }
    }

def _ema_ribbon_signal(ema9: List[Optional[float]], ema21: List[Optional[float]],
                      ema55: List[Optional[float]], closes: List[float]) -> Dict:
    """
    EMA排列分析用于趋势确认
    完美看多：价格 > EMA9 > EMA21 > EMA55
    完美看空：价格 < EMA9 < EMA21 < EMA55
    """
    if not (ema9[-1] and ema21[-1] and ema55[-1]):
        return {"alignment": "insufficient_data", "strength": 0}

    price = closes[-1]

    # 完美看多排列
    if price > ema9[-1] > ema21[-1] > ema55[-1]:
        return {"alignment": "perfect_bullish", "strength": 100}
    # 完美看空排列
    elif price < ema9[-1] < ema21[-1] < ema55[-1]:
        return {"alignment": "perfect_bearish", "strength": 100}
    # 部分看多（价格在EMA9上方）
    elif price > ema9[-1] and ema9[-1] > ema21[-1]:
        return {"alignment": "partial_bullish", "strength": 60}
    # 部分看空（价格在EMA9下方）
    elif price < ema9[-1] and ema9[-1] < ema21[-1]:
        return {"alignment": "partial_bearish", "strength": 60}
    # 中性
    else:
        return {"alignment": "neutral", "strength": 30}


def _adaptive_rsi_thresholds(atr: List[Optional[float]], atr_avg: float) -> Tuple[float, float]:
    """
    基于波动率调整RSI阈值
    高波动：使用80/20（更宽范围）
    正常：使用70/30（标准）
    低波动：使用65/35（更紧）
    """
    if not atr[-1] or atr_avg <= 0:
        return (70, 30)

    atr_ratio = atr[-1] / atr_avg

    if atr_ratio > 1.5:
        return (80, 20)  # 高波动
    elif atr_ratio < 0.7:
        return (65, 35)  # 低波动
    else:
        return (70, 30)  # 正常

# =========================
# Binance API
# =========================
def _binance_base_url() -> str:
    return os.getenv("BINANCE_SPOT_BASE_URL", "https://api.binance.com").rstrip("/")

def _http_timeout() -> float:
    return float(os.getenv("HTTP_TIMEOUT", "15"))

def _fetch_klines(symbol: str, interval: str, limit: int, dbg: List[str]) -> List[Dict]:
    """获取K线数据"""
    url = _binance_base_url() + "/api/v3/klines"
    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": min(limit, 1000)
    }
    
    try:
        resp = _SESS.get(url, params=params, timeout=_http_timeout())
        if resp.status_code != 200:
            dbg.append(f"Binance klines failed: status={resp.status_code}")
            return []
        
        data = resp.json()
        if not isinstance(data, list):
            dbg.append(f"Unexpected klines response type: {type(data)}")
            return []
        
        klines = []
        for k in data:
            klines.append({
                "open_time": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": k[6],
                "quote_volume": float(k[7]),
                "trades": k[8],
            })
        return klines
    
    except Exception as e:
        dbg.append(f"Binance klines exception: {repr(e)}")
        return []

def _generate_signals(closes: List[float], highs: List[float], lows: List[float],
                     volumes: List[float], DIF_line: List, DEA_line: List,
                     histogram: List, rsi: List, ema9: List, ema21: List,
                     ema55: List, bb_upper: List, bb_lower: List, bb_mid: List,
                     adx: List, atr: List, obv: List,
                     volume_analysis: Dict, divergences: Dict,
                     market_regime: Dict) -> Dict:
    """
    增强信号生成系统 + 加权评分
    完全重写的信号生成逻辑
    """
    if len(closes) < 2:
        return {
            "overall_signal": "INSUFFICIENT_DATA",
            "signal_score": 0,
            "confidence": 0,
            "direction": "neutral",
            "scores": {"trend": 0, "momentum": 0, "volume": 0, "volatility": 0, "overall": 0},
            "market_regime": market_regime,
            "key_signals": [],
            "warnings": ["数据不足"],
            "details": {}
        }

    current_price = closes[-1]

    # 状态权重配置
    REGIME_WEIGHTS = {
        "TRENDING_UP": {"trend": 1.5, "momentum": 1.0, "volume": 0.8, "volatility": 0.7},
        "TRENDING_DOWN": {"trend": 1.5, "momentum": 1.0, "volume": 0.8, "volatility": 0.7},
        "RANGING": {"trend": 0.5, "momentum": 1.3, "volume": 1.0, "volatility": 1.2},
        "VOLATILE": {"trend": 0.7, "momentum": 0.8, "volume": 1.0, "volatility": 1.5},
        "INSUFFICIENT_DATA": {"trend": 1.0, "momentum": 1.0, "volume": 1.0, "volatility": 1.0}
    }

    regime_type = market_regime.get("regime", "RANGING")
    regime_confidence = market_regime.get("confidence", 0.5)
    weights = REGIME_WEIGHTS.get(regime_type, REGIME_WEIGHTS["RANGING"])

    # ========== 1. 趋势信号（0-100分）==========
    trend_score = 0
    trend_components = []

    # EMA排列（25分）
    if ema9[-1] and ema21[-1] and ema55[-1]:
        if current_price > ema9[-1] > ema21[-1] > ema55[-1]:
            trend_score += 25
            trend_components.append("EMA完美看多排列")
        elif current_price < ema9[-1] < ema21[-1] < ema55[-1]:
            trend_score -= 25
            trend_components.append("EMA完美看空排列")
        elif current_price > ema9[-1] and ema9[-1] > ema21[-1]:
            trend_score += 15
            trend_components.append("EMA部分看多")
        elif current_price < ema9[-1] and ema9[-1] < ema21[-1]:
            trend_score -= 15
            trend_components.append("EMA部分看空")

    # MACD位置（25分）
    if DIF_line[-1] is not None and DEA_line[-1] is not None:
        if DIF_line[-1] > DEA_line[-1]:
            macd_strength = min(abs(histogram[-1]) / current_price * 1000 if histogram[-1] else 0, 1.0)
            trend_score += 25 * macd_strength
            if macd_strength > 0.5:
                trend_components.append(f"MACD看多(强度{macd_strength:.1f})")
        else:
            macd_strength = min(abs(histogram[-1]) / current_price * 1000 if histogram[-1] else 0, 1.0)
            trend_score -= 25 * macd_strength
            if macd_strength > 0.5:
                trend_components.append(f"MACD看空(强度{macd_strength:.1f})")

    # ADX强度确认（25分）
    if adx[-1] is not None:
        if adx[-1] > 25:
            # 强趋势确认
            if trend_score > 0:
                trend_score += 20 * min((adx[-1] - 25) / 25, 1.0)
                trend_components.append(f"ADX确认强趋势({adx[-1]:.1f})")
            elif trend_score < 0:
                trend_score -= 20 * min((adx[-1] - 25) / 25, 1.0)
                trend_components.append(f"ADX确认强趋势({adx[-1]:.1f})")

    # MACD金叉/死叉（25分）
    macd_cross = "none"
    if DIF_line[-1] and DEA_line[-1] and DIF_line[-2] and DEA_line[-2]:
        prev_diff = DIF_line[-2] - DEA_line[-2]
        curr_diff = DIF_line[-1] - DEA_line[-1]
        if prev_diff < 0 and curr_diff > 0:
            trend_score += 25
            macd_cross = "golden_cross"
            trend_components.append("MACD金叉")
        elif prev_diff > 0 and curr_diff < 0:
            trend_score -= 25
            macd_cross = "death_cross"
            trend_components.append("MACD死叉")

    trend_score = max(-100, min(100, trend_score))

    # ========== 2. 动量信号（0-100分）==========
    momentum_score = 0
    momentum_components = []

    # RSI位置（自适应阈值）（40分）
    if rsi[-1] is not None and atr[-1] is not None:
        valid_atr = [v for v in atr[-20:] if v is not None]
        atr_avg = sum(valid_atr) / len(valid_atr) if valid_atr else atr[-1]
        upper_threshold, lower_threshold = _adaptive_rsi_thresholds(atr, atr_avg)

        rsi_zone = "neutral"
        if rsi[-1] > upper_threshold:
            rsi_zone = "overbought"
            if regime_type == "RANGING":
                momentum_score -= 40
                momentum_components.append(f"RSI超买({rsi[-1]:.1f}>{upper_threshold})")
            else:
                momentum_score -= 20  # 趋势中超买不一定看跌
                momentum_components.append(f"RSI接近超买({rsi[-1]:.1f})")
        elif rsi[-1] < lower_threshold:
            rsi_zone = "oversold"
            if regime_type == "RANGING":
                momentum_score += 40
                momentum_components.append(f"RSI超卖({rsi[-1]:.1f}<{lower_threshold})")
            else:
                momentum_score += 20
                momentum_components.append(f"RSI接近超卖({rsi[-1]:.1f})")
        elif rsi[-1] > upper_threshold - 10:
            rsi_zone = "approaching_overbought"
            momentum_components.append(f"RSI接近超买区({rsi[-1]:.1f})")
        elif rsi[-1] < lower_threshold + 10:
            rsi_zone = "approaching_oversold"
            momentum_components.append(f"RSI接近超卖区({rsi[-1]:.1f})")

    # RSI背离检测（30分）
    if divergences.get("rsi_bullish"):
        momentum_score += 30
        momentum_components.append("RSI看多背离")
    elif divergences.get("rsi_bearish"):
        momentum_score -= 30
        momentum_components.append("RSI看跌背离")

    # MACD柱状图动量（30分）
    if histogram[-1] is not None and histogram[-2] is not None:
        if histogram[-1] > 0 and histogram[-1] > histogram[-2]:
            momentum_score += 20
            momentum_components.append("MACD柱状图增长")
        elif histogram[-1] < 0 and histogram[-1] < histogram[-2]:
            momentum_score -= 20
            momentum_components.append("MACD柱状图下降")

    momentum_score = max(-100, min(100, momentum_score))

    # ========== 3. 成交量信号（0-100分）==========
    volume_score = 0
    volume_components = []

    # 成交量比率（40分）
    volume_ratio = volume_analysis.get("volume_ratio", 1.0)
    if volume_ratio > 2.0:
        if closes[-1] > closes[-2]:
            volume_score += 40
            volume_components.append(f"成交量突破({volume_ratio:.1f}x)伴随价格上涨")
        else:
            volume_score -= 40
            volume_components.append(f"成交量突破({volume_ratio:.1f}x)伴随价格下跌")
    elif volume_ratio > 1.5:
        if closes[-1] > closes[-2]:
            volume_score += 25
            volume_components.append(f"成交量放大({volume_ratio:.1f}x)")
        else:
            volume_score -= 25

    # OBV趋势方向（30分）
    if len(obv) >= 20:
        obv_change = obv[-1] - obv[-20]
        price_change = closes[-1] - closes[-20]
        if obv_change > 0 and price_change > 0:
            volume_score += 30
            volume_components.append("OBV与价格同步上涨")
        elif obv_change < 0 and price_change < 0:
            volume_score -= 30
            volume_components.append("OBV与价格同步下跌")

    # 价格-成交量背离（30分）
    pv_divergence = volume_analysis.get("price_volume_divergence", "none")
    if pv_divergence == "bearish":
        volume_score -= 30
        volume_components.append("价格-成交量看跌背离")
    elif pv_divergence == "bullish":
        volume_score += 30
        volume_components.append("价格-成交量看多背离")

    volume_score = max(-100, min(100, volume_score))

    # ========== 4. 波动率/风险信号（0-100分）==========
    volatility_score = 0
    volatility_components = []

    # 布林带位置（40分）
    bb_position = 0.5
    if bb_upper[-1] and bb_lower[-1]:
        bb_width = bb_upper[-1] - bb_lower[-1]
        bb_position = (current_price - bb_lower[-1]) / bb_width if bb_width > 0 else 0.5

        if bb_position > 1.0:
            volatility_score -= 20
            volatility_components.append("突破布林上轨")
        elif bb_position > 0.8:
            volatility_score -= 10
            volatility_components.append("接近布林上轨")
        elif bb_position < 0.0:
            volatility_score += 20
            volatility_components.append("跌破布林下轨")
        elif bb_position < 0.2:
            volatility_score += 10
            volatility_components.append("接近布林下轨")

    # ATR水平（30分）
    if atr[-1] is not None:
        valid_atr = [v for v in atr[-20:] if v is not None]
        atr_avg = sum(valid_atr) / len(valid_atr) if valid_atr else atr[-1]
        atr_ratio = atr[-1] / atr_avg if atr_avg > 0 else 1.0

        if atr_ratio > 1.5:
            volatility_score -= 15
            volatility_components.append(f"ATR升高({atr_ratio:.1f}x)风险增加")

    # 背离警告（30分）
    if divergences.get("macd_bullish") or divergences.get("rsi_bullish"):
        volatility_score += 20
        volatility_components.append("检测到看多背离")
    elif divergences.get("macd_bearish") or divergences.get("rsi_bearish"):
        volatility_score -= 20
        volatility_components.append("检测到看跌背离")

    volatility_score = max(-100, min(100, volatility_score))

    # ========== 计算加权总分 ==========
    weighted_sum = (
        trend_score * weights["trend"] +
        momentum_score * weights["momentum"] +
        volume_score * weights["volume"] +
        volatility_score * weights["volatility"]
    )
    total_weight = sum(weights.values())
    base_score = weighted_sum / total_weight

    # 按状态置信度调整
    final_score = base_score * (0.7 + 0.3 * regime_confidence)

    # ========== 置信度计算 ==========
    # 统计有多少个信号类别有明确方向
    signal_agreement = 0
    positive_categories = 0
    negative_categories = 0

    if abs(trend_score) > 20:
        signal_agreement += 1
        if trend_score > 0:
            positive_categories += 1
        else:
            negative_categories += 1

    if abs(momentum_score) > 20:
        signal_agreement += 1
        if momentum_score > 0:
            positive_categories += 1
        else:
            negative_categories += 1

    if abs(volume_score) > 15:
        signal_agreement += 1
        if volume_score > 0:
            positive_categories += 1
        else:
            negative_categories += 1

    # 置信度：信号一致性 + 状态置信度
    if positive_categories >= 3 or negative_categories >= 3:
        confidence = 0.8
    elif positive_categories >= 2 or negative_categories >= 2:
        confidence = 0.6
    else:
        confidence = 0.4

    confidence = confidence * regime_confidence

    # ========== 最终分类 ==========
    if final_score > 40 and confidence > 0.6:
        overall_signal = "STRONG_BULLISH"
        direction = "bullish"
    elif final_score > 15:
        overall_signal = "BULLISH"
        direction = "bullish"
    elif final_score < -40 and confidence > 0.6:
        overall_signal = "STRONG_BEARISH"
        direction = "bearish"
    elif final_score < -15:
        overall_signal = "BEARISH"
        direction = "bearish"
    else:
        overall_signal = "NEUTRAL"
        direction = "neutral"

    # ========== 组装关键信号和警告 ==========
    key_signals = []
    warnings = []

    # 选择最强的信号
    all_components = [
        (abs(trend_score), trend_components),
        (abs(momentum_score), momentum_components),
        (abs(volume_score), volume_components)
    ]
    all_components.sort(reverse=True, key=lambda x: x[0])

    for score, components in all_components[:3]:
        key_signals.extend(components[:2])  # 每类最多2个

    # 添加警告
    if volatility_components:
        warnings.extend(volatility_components[:2])

    if regime_type == "VOLATILE":
        warnings.append(f"当前处于高波动状态（置信度{regime_confidence:.2f}）")

    # ========== 详细信息 ==========
    details = {
        "macd_cross": macd_cross,
        "rsi_zone": rsi_zone if 'rsi_zone' in locals() else "unknown",
        "trend_alignment": _ema_ribbon_signal(ema9, ema21, ema55, closes).get("alignment", "unknown"),
        "volume_status": volume_analysis.get("volume_trend", "unknown"),
        "bb_position": round(bb_position, 2),
        "divergences": {
            "rsi_bullish": divergences.get("rsi_bullish", False),
            "rsi_bearish": divergences.get("rsi_bearish", False),
            "macd_bullish": divergences.get("macd_bullish", False),
            "macd_bearish": divergences.get("macd_bearish", False)
        }
    }

    return {
        "overall_signal": overall_signal,
        "signal_score": round(final_score, 2),
        "confidence": round(confidence, 2),
        "direction": direction,
        "scores": {
            "trend": round(trend_score, 1),
            "momentum": round(momentum_score, 1),
            "volume": round(volume_score, 1),
            "volatility": round(volatility_score, 1),
            "overall": round(final_score, 1)
        },
        "market_regime": market_regime,
        "key_signals": key_signals[:5],  # 最多5个关键信号
        "warnings": warnings[:3],  # 最多3个警告
        "details": details
    }

# =========================
# Main
# =========================
def run_node(node):
    dbg = []
    t0 = time.time()
    
    # 解析输入
    symbol_raw = node['Inputs'][0].get('Context')
    if not symbol_raw or not symbol_raw.strip():
        result = {
            "ok": False,
            "error": "Symbol is required but not provided (e.g., BTCUSDT, ETHUSDT)",
            "debug": ["Missing required input: Symbol"]
        }
        Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False, indent=2)
        return Outputs
    
    symbol = symbol_raw.strip().upper()
    interval = (node['Inputs'][1].get('Context') or "1d").strip().lower()
    limit = node['Inputs'][2].get('Num') or 60
    
    try:
        limit = int(limit)
    except:
        limit = 60
    
    # 验证interval
    valid_intervals = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"]
    if interval not in valid_intervals:
        interval = "1d"
    
    dbg.append(f"Fetching {symbol} {interval} klines, limit={limit}")
    
    # 获取K线数据
    klines = _fetch_klines(symbol, interval, limit, dbg)
    
    if not klines:
        result = {
            "ok": False,
            "error": "Failed to fetch klines",
            "debug": dbg,
            "symbol": symbol,
            "interval": interval
        }
        Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False, indent=2)
        return Outputs
    
    # 提取收盘价序列
    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    volumes = [k["volume"] for k in klines]

    # 计算技术指标 - 更新参数
    DIF_line, DEA_line, histogram = _macd(closes, fast=8, slow=17, signal=6)  # 更快的MACD参数
    rsi = _rsi(closes)
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)

    # 计算多周期EMA（替换原有的ema12/ema26）
    ema9 = _ema(closes, 9)
    ema21 = _ema(closes, 21)
    ema55 = _ema(closes, 55)

    bb_upper, bb_mid, bb_lower = _bollinger_bands(closes)

    # 新增指标
    adx, plus_di, minus_di = _adx(highs, lows, closes)
    atr = _atr(highs, lows, closes)
    obv = _obv(closes, volumes)

    # 成交量分析
    volume_analysis = _volume_analysis(volumes, closes, obv)

    # 背离检测
    divergences = _detect_divergences(closes, rsi, DIF_line)

    # 市场状态识别
    market_regime = _detect_market_regime(
        closes, highs, lows, volumes,
        adx, atr, bb_upper, bb_lower,
        sma20, sma50
    )

    # 生成信号（新的加权系统）
    signals = _generate_signals(
        closes, highs, lows, volumes,
        DIF_line, DEA_line, histogram,
        rsi, ema9, ema21, ema55,
        bb_upper, bb_lower, bb_mid,
        adx, atr, obv,
        volume_analysis, divergences,
        market_regime
    )

    # 计算额外统计
    price_high_period = max(highs)
    price_low_period = min(lows)
    avg_volume = sum(volumes) / len(volumes) if volumes else 0

    # 组装结果
    dt_ms = int((time.time() - t0) * 1000)

    result = {
        "ok": True,
        "symbol": symbol,
        "interval": interval,
        "kline_count": len(klines),
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "latency_ms": dt_ms,

        # 当前价格信息
        "current": {
            "price": closes[-1],
            "open": klines[-1]["open"],
            "high": klines[-1]["high"],
            "low": klines[-1]["low"],
            "volume": klines[-1]["volume"],
        },

        # 周期统计
        "period_stats": {
            "high": price_high_period,
            "low": price_low_period,
            "range_pct": round((price_high_period - price_low_period) / price_low_period * 100, 2),
            "avg_volume": round(avg_volume, 2),
            "start_price": closes[0],
            "end_price": closes[-1],
            "period_change_pct": round((closes[-1] - closes[0]) / closes[0] * 100, 2),
        },

        # 完整技术指标
        "indicators": {
            # 趋势指标
            "ema9": ema9[-1],
            "ema21": ema21[-1],
            "ema55": ema55[-1],
            "sma20": sma20[-1],
            "sma50": sma50[-1],

            # 动量指标
            "macd": DIF_line[-1],
            "macd_signal": DEA_line[-1],
            "macd_histogram": histogram[-1],
            "rsi": rsi[-1],

            # 趋势强度
            "adx": adx[-1],
            "plus_di": plus_di[-1],
            "minus_di": minus_di[-1],

            # 波动率
            "atr": atr[-1],
            "bb_upper": bb_upper[-1],
            "bb_mid": bb_mid[-1],
            "bb_lower": bb_lower[-1],

            # 成交量
            "obv": obv[-1],
        },

        # 新的信号系统（完全替换旧signals）
        "signals": signals,

        # 最近5根K线
        "recent_klines": klines[-5:],

        "debug": dbg
    }

    Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False, indent=2)
    return Outputs
