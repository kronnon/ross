"""
信号生成模块 v5

支持:
- 1-2-3形态 + Ross Hook
- Ledge旗杆形态
- Trading Range交易区间
- RSI过滤
- KDJ过滤（v5 新增）
- BOLL过滤（v5 新增）
- EMA过滤（v5 新增）
- 多周期确认
- 形态破坏止损价（v5 新增）

v5 更新：
- 新增 KDJ/BOLL/EMA 过滤器
- 支持 skip_ross_hook 配置
- 支持 breakout_lookahead 参数
"""

from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass
import random

@dataclass
class PatternSignal:
    """形态信号"""
    side: str                  # 'long' or 'short'
    pattern_name: str         # '1-2-3', 'Ledge', 'Trading Range', 'Ross Hook'
    entry_price: float         # 入场价格
    stop_loss: float          # 止损价格
    take_profit: float        # 止盈价格
    thrust: float = 0.0       # 突破幅度
    confidence: float = 0.5   # 置信度 0-1
    metadata: Dict = None     # 额外信息
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

class SignalGenerator:
    """信号生成器 - v5 增强版"""
    
    def __init__(self, config):
        self.config = config
        self.lookback_bars = config.lookback_bars
        self.min_thrust = config.min_thrust
        
        # v5 新增参数
        self.max_lookback = getattr(config, 'max_lookback', 10)
        self.pattern_lookback = getattr(config, 'pattern_lookback', 2)
        self.min_bars_before_signal = getattr(config, 'min_bars_before_signal', 15)
        self.hook_search_range = getattr(config, 'hook_search_range', 8)
        self.confidence_threshold = getattr(config, 'confidence_threshold', 1.5)
        self.skip_ross_hook = getattr(config, 'skip_ross_hook', False)
        self.breakout_lookahead = getattr(config, 'breakout_lookahead', 3)
    
    def reset_pattern_states(self):
        """重置形态状态（回测引擎调用）"""
        pass  # 当前实现无状态，保留接口兼容
    
    # ==================== 辅助函数 ====================
    
    def get_rsi(self, prices: List[float], idx: int, period: int = 14) -> Optional[float]:
        """计算RSI"""
        if idx < period:
            return None
        
        gains = []
        losses = []
        for i in range(idx - period + 1, idx + 1):
            if i > 0:
                change = prices[i] - prices[i-1]
                gains.append(change if change > 0 else 0)
                losses.append(abs(change) if change < 0 else 0)
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def get_kdj(self, highs: List[float], lows: List[float], closes: List[float],
                idx: int, period: int = 9) -> Optional[Dict]:
        """
        计算KDJ指标（v5 新增）
        
        Returns:
            {'k': K值, 'd': D值, 'j': J值}
        """
        if idx < period:
            return None
        
        # 计算 RSV
        high_n = max(highs[idx - period + 1:idx + 1])
        low_n = min(lows[idx - period + 1:idx + 1])
        
        if high_n == low_n:
            return None

        # 简化版 KDJ（使用平滑因子）
        # K = 2/3 * K_prev + 1/3 * RSV
        # D = 2/3 * D_prev + 1/3 * K
        # J = 3 * K - 2 * D
        
        # 初始化 K, D
        k = 50.0
        d = 50.0
        
        # 递归计算
        for i in range(max(period, idx - period * 3), idx + 1):
            if i < period:
                continue
            h = max(highs[i - period + 1:i + 1])
            l = min(lows[i - period + 1:i + 1])
            if h == l:
                continue
            rsv_i = (closes[i] - l) / (h - l) * 100
            k = 2/3 * k + 1/3 * rsv_i
            d = 2/3 * d + 1/3 * k
        
        j = 3 * k - 2 * d
        
        return {'k': k, 'd': d, 'j': j}
    
    def get_boll(self, prices: List[float], idx: int, period: int = 20, 
                 std_mult: float = 2.0) -> Optional[Dict]:
        """
        计算布林带（v5 新增）
        
        Returns:
            {'upper': 上轨, 'middle': 中轨, 'lower': 下轨}
        """
        if idx < period:
            return None
        
        segment = prices[idx - period + 1:idx + 1]
        middle = sum(segment) / period
        
        # 计算标准差
        variance = sum((p - middle) ** 2 for p in segment) / period
        std = variance ** 0.5
        
        upper = middle + std_mult * std
        lower = middle - std_mult * std
        
        return {'upper': upper, 'middle': middle, 'lower': lower}
    
    def get_ema(self, prices: List[float], idx: int, period: int = 20) -> Optional[float]:
        """计算EMA"""
        if idx < period:
            return None
        
        # 简单EMA计算
        multiplier = 2 / (period + 1)
        ema = prices[idx - period + 1]
        
        for i in range(idx - period + 2, idx + 1):
            ema = (prices[i] - ema) * multiplier + ema
        
        return ema
    
    def get_ht_trend(self, ht_prices: List[float]) -> str:
        """
        判断大周期趋势方向
        返回: 'up', 'down', 'neutral'
        """
        if len(ht_prices) < 20:
            return 'neutral'
        
        # 使用最近20根K线判断
        recent = ht_prices[-20:]
        first_half = recent[:10]
        second_half = recent[10:]
        
        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)
        
        diff_pct = (avg_second - avg_first) / avg_first * 100
        
        if diff_pct > 0.3:  # 上涨0.3%以上
            return 'up'
        elif diff_pct < -0.3:
            return 'down'
        return 'neutral'
    
    def check_multi_timeframe_confirm(self, ht_prices: List[float], direction: str) -> Tuple[bool, str]:
        """
        多周期确认
        检查大周期趋势是否与信号方向一致
        
        Args:
            ht_prices: 大周期收盘价列表
            direction: 信号方向 ('up' 或 'down')
        
        Returns:
            (是否确认, 原因)
        """
        if not getattr(self.config, 'higher_timeframe', ''):
            return True, ""
        
        if not ht_prices or len(ht_prices) < 10:
            return True, ""  # 数据不足，不过滤
        
        ht_trend = self.get_ht_trend(ht_prices)
        
        if ht_trend == 'neutral':
            return True, ""  # 中性趋势，不过滤
        
        # 大周期上涨，只做多
        if direction == 'up' and ht_trend == 'down':
            return False, f"大周期趋势向下({ht_trend})，禁止做多"
        
        # 大周期下跌，只做空
        if direction == 'down' and ht_trend == 'up':
            return False, f"大周期趋势向上({ht_trend})，禁止做空"
        
        return True, ""
    
    # ==================== 1-2-3形态识别 ====================
    
    def find_123_pattern(self, prices: List[float], current_idx: int, 
                         max_lookback: int = None, pattern_lookback: int = None,
                         p2_p3_lookback: int = None,
                         highs: List[float] = None, lows: List[float] = None) -> Optional[Dict]:
        """
        寻找1-2-3形态（v5 精细化版本）
        
        Args:
            max_lookback: P1回看范围（往前多少根K线找P1）
            pattern_lookback: P1局部极值判断（前后几根必须比P1低/高）
            p2_p3_lookback: P2/P3 回看范围
            highs: 最高价列表（用于判断局部高点）
            lows: 最低价列表（用于判断局部低点）
        
        注意:
            - 做空形态（P1是高点）：用 highs 判断局部高点
            - 做多形态（P1是低点）：用 lows 判断局部低点
            - 如果 highs/lows 为 None，回退到用 prices (closes)
        """
        max_lookback = max_lookback or self.max_lookback
        pattern_lookback = pattern_lookback or self.pattern_lookback
        p2_p3_lookback = p2_p3_lookback or self.config.p2_p3_lookback
        
        if current_idx < 10 or current_idx - max_lookback < 0:
            return None
        
        # 从当前往前找 P1
        for i in range(current_idx - 3, max(3, current_idx - max_lookback), -1):
            # 使用 highs 判断局部高点（做空形态）
            # 使用 lows 判断局部低点（做多形态）
            p1_high = highs[i] if highs else prices[i]
            p1_low = lows[i] if lows else prices[i]
            is_local_high = True
            is_local_low = True
            
            # 检查是否为局部极值
            for j in range(max(0, i - pattern_lookback), i):
                # 判断局部高点：用 highs
                check_high = highs[j] if highs else prices[j]
                if check_high >= p1_high:
                    is_local_high = False
                # 判断局部低点：用 lows
                check_low = lows[j] if lows else prices[j]
                if check_low <= p1_low:
                    is_local_low = False
            
            if not is_local_high and not is_local_low:
                continue
            
            # 找 P2（回调点）
            # 做空形态：P2 是回调低点，用 lows 找最低点
            # 做多形态：P2 是反弹高点，用 highs 找最高点
            p2_idx = None
            p2_price = None
            
            if is_local_high:
                # 做空：找回调最低点
                search_low = lows if lows else prices
                min_low = search_low[i + 1]
                min_idx = i + 1
                for j in range(i + 1, min(len(prices), i + p2_p3_lookback)):
                    if search_low[j] < min_low:
                        min_low = search_low[j]
                        min_idx = j
                # 确认有回调（最低点比 P1 低点低）
                p1_low_val = lows[i] if lows else prices[i]
                if min_low < p1_low_val:
                    p2_idx = min_idx
                    p2_price = min_low
            else:
                # 做多：找反弹最高点
                search_high = highs if highs else prices
                max_high = search_high[i + 1]
                max_idx = i + 1
                for j in range(i + 1, min(len(prices), i + p2_p3_lookback)):
                    if search_high[j] > max_high:
                        max_high = search_high[j]
                        max_idx = j
                # 确认有反弹（最高点比 P1 高点高）
                p1_high_val = highs[i] if highs else prices[i]
                if max_high > p1_high_val:
                    p2_idx = max_idx
                    p2_price = max_high
            
            if not p2_idx:
                continue
            
            # 找 P3（恢复点，但未突破 P1）
            # 做空形态：P3 是反弹高点（未突破 P1 高点），用 highs
            # 做多形态：P3 是回调低点（未跌破 P1 低点），用 lows
            p3_idx = None
            p3_price = None
            
            # 边界检查：确保 p2_idx + 1 不超出范围
            if p2_idx + 1 >= len(prices):
                continue
            
            if is_local_high:
                # 做空：找反弹最高点（未突破 P1）
                search_high = highs if highs else prices
                max_high = search_high[p2_idx + 1]
                max_idx = p2_idx + 1
                for j in range(p2_idx + 1, min(len(prices), p2_idx + p2_p3_lookback)):
                    if search_high[j] > max_high:
                        max_high = search_high[j]
                        max_idx = j
                # P3 必须未突破 P1 高点
                if max_high < p1_high:
                    p3_idx = max_idx
                    p3_price = max_high
            else:
                # 做多：找回调最低点（未跌破 P1）
                search_low = lows if lows else prices
                min_low = search_low[p2_idx + 1]
                min_idx = p2_idx + 1
                for j in range(p2_idx + 1, min(len(prices), p2_idx + p2_p3_lookback)):
                    if search_low[j] < min_low:
                        min_low = search_low[j]
                        min_idx = j
                # P3 必须未跌破 P1 低点
                if min_low > p1_low:
                    p3_idx = min_idx
                    p3_price = min_low
            
            if p3_idx:
                pattern_type = 'high' if is_local_high else 'low'
                # P1 价格：高点用 high，低点用 low
                p1_price = p1_high if is_local_high else p1_low
                return {
                    'type': pattern_type,
                    'p1': (i, p1_price),
                    'p2': (p2_idx, p2_price),
                    'p3': (p3_idx, p3_price),
                }
        
        return None
    
    def find_ross_hook(self, prices: List[float], pattern_idx: int, 
                       pattern_type: str, hook_search_range: int = None) -> Optional[Dict]:
        """
        寻找Ross Hook
        突破1-2-3后的第一次"失败"
        """
        hook_search_range = hook_search_range or self.hook_search_range
        
        if pattern_idx + 2 >= len(prices):
            return None
        
        if pattern_type == 'low':
            # 上涨趋势：找未能创新高（回调）
            for i in range(pattern_idx, min(len(prices), pattern_idx + hook_search_range)):
                if i > 0 and prices[i] < prices[i-1]:
                    return {'index': i, 'price': prices[i]}
        else:
            # 下跌趋势：找未能创新低（反弹）
            for i in range(pattern_idx, min(len(prices), pattern_idx + hook_search_range)):
                if i > 0 and prices[i] > prices[i-1]:
                    return {'index': i, 'price': prices[i]}
        
        return None
    
    # ==================== Ledge旗杆形态识别 ====================
    
    def find_ledge(self, prices: List[float], highs: List[float], lows: List[float],
                   current_idx: int, lookback: int = 20) -> Optional[Dict]:
        """
        寻找Ledge（旗杆）形态
        
        旗杆特征:
        - 连续的趋势运动（上涨/下跌）
        - 伴随成交量放大
        - 旗杆后盘整（回调/反弹）
        - 突破盘整区域后入场
        """
        if current_idx < lookback:
            return None
        
        start_idx = current_idx - lookback
        segment = prices[start_idx:current_idx]

        # 分析趋势
        first_half = segment[:len(segment)//2]
        second_half = segment[len(segment)//2:]
        
        first_high = max(first_half)
        first_low = min(first_half)
        second_high = max(second_half)
        second_low = min(second_half)
        
        # 上涨旗杆：前半段上涨，后半段盘整
        if first_high > first_low * 1.02 and second_high < first_high * 1.02:
            # 回调幅度不超过上涨的50%
            pullback = (first_high - second_low) / (first_high - first_low)
            if 0.2 < pullback < 0.8:
                return {
                    'type': 'bullish_ledge',
                    'breakout_idx': current_idx,
                    'pole_high': first_high,
                    'pole_low': first_low,
                    'consolidation_high': second_high,
                    'consolidation_low': second_low,
                }
        
        # 下跌旗杆：前半段下跌，后半段盘整
        if first_low < first_high * 0.98 and second_low > first_low * 0.98:
            pullback = (second_high - first_low) / (first_high - first_low)
            if 0.2 < pullback < 0.8:
                return {
                    'type': 'bearish_ledge',
                    'breakout_idx': current_idx,
                    'pole_high': first_high,
                    'pole_low': first_low,
                    'consolidation_high': second_high,
                    'consolidation_low': second_low,
                }
        
        return None
    
    # ==================== Trading Range交易区间识别 ====================
    
    def find_trading_range(self, prices: List[float], highs: List[float], 
                          lows: List[float], current_idx: int, 
                          lookback: int = 30) -> Optional[Dict]:
        """
        寻找Trading Range（交易区间）
        
        特征:
        - 价格在一定范围内波动
        - 多次触及上下轨
        - 突破区间后入场
        """
        if current_idx < lookback:
            return None
        
        start_idx = current_idx - lookback
        segment_prices = prices[start_idx:current_idx]
        segment_highs = highs[start_idx:current_idx]
        segment_lows = lows[start_idx:current_idx]
        
        # 计算区间
        high = max(segment_highs)
        low = min(segment_lows)
        range_pct = (high - low) / low * 100
        
        # 区间幅度在1-15%之间
        if range_pct < 1.0 or range_pct > 15.0:
            return None
        
        # 检查是否多次触及上下轨
        touch_high = sum(1 for p in segment_prices if p >= high * 0.998)
        touch_low = sum(1 for p in segment_prices if p <= low * 1.002)
        
        if touch_high < 2 or touch_low < 2:
            return None
        
        # 当前价格位置
        current_price = prices[current_idx]
        position_pct = (current_price - low) / (high - low) if high > low else 0.5
        
        return {
            'type': 'trading_range',
            'high': high,
            'low': low,
            'range_pct': range_pct,
            'touch_high': touch_high,
            'touch_low': touch_low,
            'position_pct': position_pct,
            'breakout_idx': current_idx,
        }
    
    # ==================== 过滤器 ====================
    
    def check_rsi_filter(self, prices: List[float], direction: str) -> Tuple[bool, str]:
        """
        RSI过滤
        - 多头: RSI < 70 可做多，RSI > 80 禁止做多
        - 空头: RSI > 30 可做空，RSI < 20 禁止做空
        """
        if not getattr(self.config, 'enable_rsi_filter', False):
            return True, ""
        
        rsi_period = getattr(self.config, 'rsi_period', 14)
        rsi_overbought = getattr(self.config, 'rsi_overbought', 70)
        rsi_oversold = getattr(self.config, 'rsi_oversold', 30)
        
        # 获取最近一根K线的RSI
        rsi = self.get_rsi(prices, len(prices) - 1, rsi_period)
        
        if rsi is None:
            return True, ""  # 数据不足，不过滤
        
        if direction == 'up':
            # 做多检查
            if rsi > rsi_overbought:
                return False, f"RSI超买({rsi:.1f}>{rsi_overbought})"
        else:
            # 做空检查
            if rsi < rsi_oversold:
                return False, f"RSI超卖({rsi:.1f}<{rsi_oversold})"
        
        return True, ""
    
    def check_kdj_filter(self, highs: List[float], lows: List[float], 
                         closes: List[float], direction: str) -> Tuple[bool, str]:
        """
        KDJ过滤（v5 新增）
        - 多头: K < 80 且 J < 100 可做多
        - 空头: K > 20 且 J > 0 可做空
        """
        if not getattr(self.config, 'enable_kdj_filter', False):
            return True, ""
        
        kdj_period = getattr(self.config, 'kdj_period', 9)
        kdj_k_overbought = getattr(self.config, 'kdj_k_overbought', 80)
        kdj_k_oversold = getattr(self.config, 'kdj_k_oversold', 20)
        kdj_j_overbought = getattr(self.config, 'kdj_j_overbought', 100)
        kdj_j_oversold = getattr(self.config, 'kdj_j_oversold', 0)
        
        idx = len(closes) - 1
        kdj = self.get_kdj(highs, lows, closes, idx, kdj_period)
        
        if kdj is None:
            return True, ""  # 数据不足，不过滤
        
        k, j = kdj['k'], kdj['j']
        
        if direction == 'up':
            # 做多检查
            if k > kdj_k_overbought:
                return False, f"K值超买({k:.1f}>{kdj_k_overbought})"
            if j > kdj_j_overbought:
                return False, f"J值超买({j:.1f}>{kdj_j_overbought})"
        else:
            # 做空检查
            if k < kdj_k_oversold:
                return False, f"K值超卖({k:.1f}<{kdj_k_oversold})"
            if j < kdj_j_oversold:
                return False, f"J值超卖({j:.1f}<{kdj_j_oversold})"
        
        return True, ""
    
    def check_boll_filter(self, closes: List[float], current_price: float, 
                          direction: str) -> Tuple[bool, str]:
        """
        BOLL过滤（v5 新增）
        - 多头: 价格必须在中轨上方
        - 空头: 价格必须在中轨下方
        """
        if not getattr(self.config, 'enable_boll_filter', False):
            return True, ""
        
        boll_period = getattr(self.config, 'boll_period', 20)
        boll_std = getattr(self.config, 'boll_std', 2)
        
        idx = len(closes) - 1
        boll = self.get_boll(closes, idx, boll_period, boll_std)
        
        if boll is None:
            return True, ""  # 数据不足，不过滤
        
        middle = boll['middle']
        
        if direction == 'up':
            if current_price < middle:
                return False, f"价格低于中轨({current_price:.2f}<{middle:.2f})"
        else:
            if current_price > middle:
                return False, f"价格高于中轨({current_price:.2f}>{middle:.2f})"
        
        return True, ""
    
    def check_ema_filter(self, prices: List[float], current_price: float, 
                         direction: str) -> Tuple[bool, str]:
        """
        EMA过滤（v5 新增）
        - 多头: 价格必须在EMA上方
        - 空头: 价格必须在EMA下方
        """
        if not getattr(self.config, 'enable_ema_filter', False):
            return True, ""
        
        ema_period = getattr(self.config, 'ema_period', 20)
        
        idx = len(prices) - 1
        ema = self.get_ema(prices, idx, ema_period)
        
        if ema is None:
            return True, ""  # 数据不足，不过滤
        
        if direction == 'up':
            if current_price < ema:
                return False, f"价格低于EMA({current_price:.2f}<{ema:.2f})"
        else:
            if current_price > ema:
                return False, f"价格高于EMA({current_price:.2f}>{ema:.2f})"
        
        return True, ""
    
    def check_volume(self, volume: float, current_price: float = None) -> bool:
        """成交量过滤（交易金额 = volume × price）"""
        if self.config.min_volume > 0:
            # 计算交易金额
            if current_price:
                trade_amount = volume * current_price
            else:
                trade_amount = volume  # 兼容旧逻辑
            if trade_amount < self.config.min_volume:
                return False
        return True
    
    def check_fill(self) -> bool:
        """成交率模拟"""
        if self.config.fill_rate < 1.0:
            return random.random() < self.config.fill_rate
        return True
    
    def check_breakout_confirmation(self, prices: List[float], hook_idx: int, 
                                    direction: str, highs: List[float] = None,
                                    lows: List[float] = None, 
                                    current_idx: int = None,
                                    hook_price: float = None) -> Tuple[bool, float]:
        """
        突破确认检查
        
        检查从 Hook 到当前K线之间，价格是否穿越了 Hook 价格
        
        Args:
            current_idx: 当前K线索引
            hook_price: Hook 价格（如果为 None，使用 prices[hook_idx]）
        """
        if current_idx is None or current_idx >= len(prices):
            return False, 0
        
        # 边界检查：hook_idx 不能超过 current_idx
        if hook_idx > current_idx:
            return False, 0
        
        # 使用传入的 hook_price 或从 prices 获取
        hook_price = hook_price if hook_price is not None else prices[hook_idx]
        
        if direction == 'up':
            # 做多：检查从 hook 到当前K线，最高价是否突破 Hook 价格
            if highs:
                peak_price = max(highs[hook_idx:current_idx + 1])
            else:
                peak_price = max(prices[hook_idx:current_idx + 1])
            if peak_price > hook_price:
                thrust = (peak_price - hook_price) / hook_price * 100
                return True, thrust
        else:
            # 做空：检查从 hook 到当前K线，最低价是否突破 Hook 价格
            if lows:
                trough_price = min(lows[hook_idx:current_idx + 1])
            else:
                trough_price = min(prices[hook_idx:current_idx + 1])
            if trough_price < hook_price:
                thrust = (hook_price - trough_price) / hook_price * 100
                return True, thrust
        
        return False, 0
    
    # ==================== 信号生成 ====================
    
    def _apply_filters(self, closes: List[float], highs: List[float], lows: List[float],
                       current_price: float, direction: str,
                       volume: float = None) -> bool:
        """应用所有过滤器"""
        # RSI过滤
        pass_rsi, _ = self.check_rsi_filter(closes, direction)
        if not pass_rsi:
            return False
        
        # KDJ过滤
        if highs and lows:
            pass_kdj, _ = self.check_kdj_filter(highs, lows, closes, direction)
            if not pass_kdj:
                return False
        
        # BOLL过滤
        pass_boll, _ = self.check_boll_filter(closes, current_price, direction)
        if not pass_boll:
            return False
        
        # EMA过滤
        pass_ema, _ = self.check_ema_filter(closes, current_price, direction)
        if not pass_ema:
            return False

        # 成交量过滤（volume × current_price = 交易金额）
        if volume is not None and not self.check_volume(volume, current_price):
            return False
        
        # 成交率模拟
        if not self.check_fill():
            return False
        
        return True
    
    def _build_signal(self, pattern_name: str, direction: str,
                       hook_price: float, thrust: float,
                       metadata: Dict = None) -> PatternSignal:
        """构建交易信号对象（入场价 = Hook 价格，纯净价不加滑点）"""
        # 信号只记录纯净的 hook_price，滑点在开仓时计算
        entry_price = hook_price
        
        # 止损止盈基于 hook_price 预估（实际会在开仓时重新计算）
        if direction == 'up':
            stop_loss = entry_price * (1 - self.config.stop_loss_pct / 100)
            take_profit = entry_price * (1 + self.config.take_profit_pct / 100)
        else:
            stop_loss = entry_price * (1 + self.config.stop_loss_pct / 100)
            take_profit = entry_price * (1 - self.config.take_profit_pct / 100)
        
        return PatternSignal(
            side='long' if direction == 'up' else 'short',
            pattern_name=pattern_name,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            thrust=thrust,
            confidence=min(thrust / (self.confidence_threshold / 100), 1.0),
            metadata=metadata or {},
        )
    
    def _try_123_pattern(self, closes: List[float],
                         highs: List[float], lows: List[float], current_idx: int) -> Optional[PatternSignal]:
        """尝试 1-2-3 形态入场"""
        pattern = self.find_123_pattern(closes, current_idx, highs=highs, lows=lows)
        if not pattern:
            return None
        
        # 支持 skip_ross_hook
        if self.skip_ross_hook:
            hook = {'index': pattern['p3'][0], 'price': pattern['p3'][1]}
        else:
            hook = self.find_ross_hook(closes, pattern['p3'][0], pattern['type'])
            if not hook:
                return None
        
        # 检查突破（传入 current_idx 实时判断）
        direction = 'up' if pattern['type'] == 'low' else 'down'
        breakout, thrust = self.check_breakout_confirmation(
            closes, hook['index'], direction, highs, lows, current_idx, hook['price']
        )
        
        if not breakout or thrust < self.config.min_thrust:
            return None
        
        return direction, thrust, hook, pattern
    
    def _try_ledge_pattern(self, closes: List[float],
                           highs: List[float], lows: List[float], current_idx: int) -> Optional[PatternSignal]:
        """尝试 Ledge 形态入场"""
        if not highs or not lows:
            return None
        
        ledge = self.find_ledge(closes, highs, lows, current_idx)
        if not ledge:
            return None
        
        # 用 high/low 判断是否穿越突破
        current_high = highs[current_idx]
        current_low = lows[current_idx]
        
        if ledge['type'] == 'bullish_ledge':
            # 做多：当前K线最高价突破盘整区上边界
            if current_high <= ledge['consolidation_high']:
                return None
            direction = 'up'
            pattern_type = 'low'  # 用于 find_ross_hook
        else:
            # 做空：当前K线最低价突破盘整区下边界
            if current_low >= ledge['consolidation_low']:
                return None
            direction = 'down'
            pattern_type = 'high'
        
        # 找 Ross Hook（突破后的第一次回撤）
        if self.skip_ross_hook:
            hook = {'index': current_idx, 'price': closes[current_idx]}
        else:
            hook = self.find_ross_hook(closes, ledge['breakout_idx'], pattern_type)
            if not hook:
                return None
        
        # 检查突破确认（传入 current_idx 实时判断）
        breakout, thrust = self.check_breakout_confirmation(
            closes, hook['index'], direction, highs, lows, current_idx, hook['price']
        )
        
        if not breakout or thrust < self.config.min_thrust:
            return None
        
        return direction, thrust, hook, ledge
    
    def _try_trading_range_pattern(self, closes: List[float],
                                    highs: List[float], lows: List[float], current_idx: int) -> Optional[PatternSignal]:
        """尝试 Trading Range 形态入场"""
        if not highs or not lows:
            return None
        
        tr = self.find_trading_range(closes, highs, lows, current_idx)
        if not tr:
            return None
        
        # 突破跟随：检查是否突破区间边界
        current_high = highs[current_idx]
        current_low = lows[current_idx]
        
        if current_high > tr['high']:
            # 突破上边界 → 做多
            direction = 'up'
            pattern_type = 'low'
        elif current_low < tr['low']:
            # 突破下边界 → 做空
            direction = 'down'
            pattern_type = 'high'
        else:
            return None  # 未突破，不入场
        
        # 找 Ross Hook
        if self.skip_ross_hook:
            hook = {'index': current_idx, 'price': closes[current_idx]}
        else:
            hook = self.find_ross_hook(closes, tr['breakout_idx'], pattern_type)
            if not hook:
                return None
        
        # 检查突破确认（传入 current_idx 实时判断）
        breakout, thrust = self.check_breakout_confirmation(
            closes, hook['index'], direction, highs, lows, current_idx, hook['price']
        )
        
        if not breakout or thrust < self.config.min_thrust:
            return None
        
        return direction, thrust, hook, tr
    
    def generate_signal(self, records: List[dict], current_idx: int,
                        pre_extracted: dict = None) -> Optional[PatternSignal]:
        """
        生成交易信号
        
        优先级: 1-2-3 > Ledge > Trading Range
        
        Args:
            pre_extracted: 预提取的数据字典 {'closes', 'opens', 'highs', 'lows'}
        """
        # 基本检查
        if current_idx < self.min_bars_before_signal:
            return None
        
        # 使用预提取数据或自行提取
        if pre_extracted:
            closes = pre_extracted['closes']
            opens = pre_extracted['opens']
            highs = pre_extracted.get('highs')
            lows = pre_extracted.get('lows')
            volumes = pre_extracted.get('volumes')
        else:
            closes = [r['close'] for r in records]
            opens = [r['open'] for r in records]
            highs = [r['high'] for r in records] if records and 'high' in records[0] else None
            lows = [r['low'] for r in records] if records and 'low' in records[0] else None
        
        current_price = records[current_idx]['close']
        # 成交量：优先从 pre_extracted 获取，否则从 records 获取
        volume = pre_extracted.get('volumes')[current_idx] if pre_extracted and pre_extracted.get('volumes') else records[current_idx].get('volume')
        
        # 按优先级检测形态
        # 1. 1-2-3 形态（最高优先级）
        result = self._try_123_pattern(closes, highs, lows, current_idx)
        if result:
            direction, thrust, hook, pattern = result
            if self._apply_filters(closes, highs, lows, current_price, direction, volume):
                return self._build_signal(
                    pattern_name='1-2-3 Ross Hook',
                    direction=direction,
                    hook_price=hook['price'],
                    thrust=thrust,
                    metadata={
                        'pattern_type': pattern['type'],
                        'p1': pattern['p1'],
                        'p2': pattern['p2'],
                        'p3': pattern['p3'],
                        'hook': (hook['index'], hook['price']),
                    }
                )

        # 2. Ledge 形态
        result = self._try_ledge_pattern(closes, highs, lows, current_idx)
        if result:
            direction, thrust, hook, ledge = result
            if self._apply_filters(closes, highs, lows, current_price, direction, volume):
                return self._build_signal(
                    pattern_name='Ledge Ross Hook',
                    direction=direction,
                    hook_price=hook['price'],
                    thrust=thrust,
                    metadata={
                        'ledge_type': ledge['type'],
                        'pole_high': ledge['pole_high'],
                        'pole_low': ledge['pole_low'],
                        'consolidation_high': ledge['consolidation_high'],
                        'consolidation_low': ledge['consolidation_low'],
                        'hook': (hook['index'], hook['price']),
                    }
                )

        # 3. Trading Range 形态
        result = self._try_trading_range_pattern(closes, highs, lows, current_idx)
        if result:
            direction, thrust, hook, tr = result
            if self._apply_filters(closes, highs, lows, current_price, direction, volume):
                return self._build_signal(
                    pattern_name='Trading Range Ross Hook',
                    direction=direction,
                    hook_price=hook['price'],
                    thrust=thrust,
                    metadata={
                        'range_high': tr['high'],
                        'range_low': tr['low'],
                        'range_pct': tr['range_pct'],
                        'position_pct': tr['position_pct'],
                        'hook': (hook['index'], hook['price']),
                    }
                )
        
        return None

def create_signal_generator(config) -> SignalGenerator:
    """创建信号生成器"""
    return SignalGenerator(config)
