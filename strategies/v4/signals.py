"""
信号生成模块 - 形态识别增强版

支持:
- 1-2-3形态 + Ross Hook
- Ledge旗杆形态
- Trading Range交易区间
- RSI过滤
- 多周期确认
"""

from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass
import random


@dataclass
class PatternSignal:
    """形态信号"""
    signal_type: str          # 'long' or 'short'
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
    """信号生成器 - 简化版，快速"""
    
    def __init__(self, config):
        self.config = config
        self.lookback_bars = config.lookback_bars
        self.min_thrust = config.min_thrust
    
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
    
    def get_atr(self, highs: List[float], lows: List[float], closes: List[float], 
                idx: int, period: int = 14) -> Optional[float]:
        """计算ATR（平均真实波幅）"""
        if idx < period:
            return None
        
        trs = []
        for i in range(idx - period + 1, idx + 1):
            if i == 0:
                continue
            high_low = highs[i] - lows[i]
            high_close = abs(highs[i] - closes[i-1]) if i > 0 else 0
            low_close = abs(lows[i] - closes[i-1]) if i > 0 else 0
            tr = max(high_low, high_close, low_close)
            trs.append(tr)
        
        return sum(trs) / period if trs else None
    
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
    
    def is_local_extreme(self, prices: List[float], idx: int, lookback: int = 3) -> Tuple[bool, bool]:
        """判断是否为局部极值"""
        if idx < lookback or idx >= len(prices) - 1:
            return False, False
        
        price = prices[idx]
        
        # 检查是否为局部高点
        is_high = all(prices[j] <= price for j in range(max(0, idx-lookback), idx))
        
        # 检查是否为局部低点
        is_low = all(prices[j] >= price for j in range(max(0, idx-lookback), idx))
        
        return is_high, is_low
    
    # ==================== 1-2-3形态识别 ====================
    
    def find_123_pattern(self, prices: List[float], current_idx: int, 
                         max_lookback: int = None) -> Optional[Dict]:
        """
        寻找1-2-3形态（简化版，只看最近15根）
        """
        # 限制回看范围为15根K线，加速
        max_lookback = 15
        
        if current_idx < 10 or current_idx - max_lookback < 0:
            return None
        
        # 只检查最近15根K线
        for i in range(current_idx - 3, max(5, current_idx - max_lookback), -1):
            is_high, is_low = self.is_local_extreme(prices, i, 3)
            
            if not is_high and not is_low:
                continue
            
            # 找点2（回调的局部极值 - 从上涨转为下跌，或从下跌转为上涨）
            p2_idx = None
            if is_high:
                # 下跌趋势：寻找局部低点（跌不动开始反弹）
                for j in range(i+1, min(len(prices), i+8)):
                    # 找到连续下跌后开始反弹的点
                    if j > 1 and prices[j] > prices[j-1]:
                        # 检查是否是反弹的开始（前一天是下跌）
                        if j >= 3 and prices[j-1] < prices[j-2]:
                            p2_idx = j
                            break
                        # 如果没有更早的数据，直接用这个反弹点
                        if prices[j-1] == prices[j-2]:
                            p2_idx = j
                            break
            else:
                # 上涨趋势：寻找局部高点（涨不动开始回调）
                for j in range(i+1, min(len(prices), i+8)):
                    # 找到连续上涨后开始下跌的点
                    if j > 1 and prices[j] < prices[j-1]:
                        # 检查是否是回调的开始（前一天是上涨）
                        if j >= 3 and prices[j-1] > prices[j-2]:
                            p2_idx = j
                            break
                        # 如果没有更早的数据，直接用这个回调点
                        if prices[j-1] == prices[j-2]:
                            p2_idx = j
                            break
            
            if p2_idx is None:
                continue
            
            # 找点3（恢复趋势但未突破点1）
            p3_idx = None
            if is_high:
                # 下跌后恢复下跌，但未跌破点1
                for j in range(p2_idx+1, min(len(prices), p2_idx+8)):
                    if prices[j] < prices[i]:  # 跌破点1，形态无效
                        p3_idx = None
                        break
                    if j > p2_idx and prices[j] > prices[p2_idx]:  # 反弹超过点2，找到p3
                        p3_idx = j
            else:
                # 上涨后恢复上涨，但未突破点1
                for j in range(p2_idx+1, min(len(prices), p2_idx+8)):
                    if prices[j] > prices[i]:  # 突破点1，形态无效
                        p3_idx = None
                        break
                    if j > p2_idx and prices[j] < prices[p2_idx]:  # 回调低于点2，找到p3
                        p3_idx = j
            
            if p3_idx is None:
                continue
            
            pattern_type = 'high' if is_high else 'low'
            
            return {
                'type': pattern_type,
                'p1': (i, prices[i]),
                'p2': (p2_idx, prices[p2_idx]),
                'p3': (p3_idx, prices[p3_idx]),
            }
        
        return None
    
    def find_ross_hook(self, prices: List[float], pattern_idx: int, 
                       pattern_type: str) -> Optional[Dict]:
        """
        寻找Ross Hook
        突破1-2-3后的第一次"失败"
        """
        if pattern_idx + 2 >= len(prices):
            return None
        
        if pattern_type == 'low':
            # 上涨趋势：找未能创新高（回调）
            for i in range(pattern_idx, min(len(prices), pattern_idx + 8)):
                if i > 0 and prices[i] < prices[i-1]:
                    return {'index': i, 'price': prices[i]}
        else:
            # 下跌趋势：找未能创新低（反弹）
            for i in range(pattern_idx, min(len(prices), pattern_idx + 8)):
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
        high_prices = highs[start_idx:current_idx]
        low_prices = lows[start_idx:current_idx]
        
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
    
    def check_volume(self, volume: float) -> bool:
        """成交量过滤"""
        if self.config.min_volume > 0 and volume < self.config.min_volume:
            return False
        return True
    
    def check_fill(self) -> bool:
        """成交率模拟"""
        if self.config.fill_rate < 1.0:
            return random.random() < self.config.fill_rate
        return True
    
    def check_breakout_confirmation(self, prices: List[float], hook_idx: int, 
                                    direction: str) -> Tuple[bool, float]:
        """
        突破确认检查
        """
        if hook_idx + 1 >= len(prices):
            return False, 0
        
        hook_price = prices[hook_idx]
        
        if direction == 'up':
            breakout_price = prices[hook_idx + 1]
            thrust = (breakout_price - hook_price) / hook_price * 100
            return breakout_price > hook_price, thrust
        else:
            breakout_price = prices[hook_idx + 1]
            thrust = (hook_price - breakout_price) / hook_price * 100
            return breakout_price < hook_price, thrust
    
    # ==================== 信号生成 ====================
    
    def generate_signal(self, records: List[dict], current_idx: int, 
                        positions_count: int, ht_closes: List[float] = None) -> Optional[PatternSignal]:
        """
        生成交易信号
        暂时只保留1-2-3形态（简化版）
        """
        # 基本检查
        if current_idx < self.lookback_bars:
            return None
        
        if positions_count >= self.config.max_concurrent_positions:
            return None
        
        # 提取数据
        closes = [r['close'] for r in records]
        opens = [r['open'] for r in records]
        
        # 只检查1-2-3形态
        signal = self._try_123_pattern(records, current_idx, closes, opens, None, None, ht_closes)
        return signal
    
    def _try_123_pattern(self, records: List[dict], current_idx: int,
                         closes: List[float], opens: List[float],
                         highs: List[float], lows: List[float],
                         ht_closes: List[float] = None) -> Optional[PatternSignal]:
        """尝试1-2-3形态信号"""
        
        pattern = self.find_123_pattern(closes, current_idx)
        if not pattern:
            return None
        
        hook = self.find_ross_hook(closes, pattern['p3'][0], pattern['type'])
        if not hook:
            return None
        
        # 检查突破
        direction = 'up' if pattern['type'] == 'low' else 'down'
        breakout, thrust = self.check_breakout_confirmation(closes, hook['index'], direction)
        
        if not breakout or thrust < self.config.min_thrust:
            return None
        
        # RSI过滤
        pass_rsi, rsi_reason = self.check_rsi_filter(closes, direction)
        if not pass_rsi:
            return None
        
        # 多周期确认
        if ht_closes:
            pass_ht, ht_reason = self.check_multi_timeframe_confirm(ht_closes, direction)
            if not pass_ht:
                return None
        
        # 成交量过滤
        current_volume = records[current_idx].get('qty', 0)
        if not self.check_volume(current_volume):
            return None
        
        # 成交率模拟
        if not self.check_fill():
            return None
        
        # 计算价格
        slippage = self.config.slippage_pct / 100
        base_price = opens[current_idx]
        
        if direction == 'up':
            entry_price = base_price * (1 + slippage)
            stop_loss = entry_price * (1 - self.config.stop_loss_pct / 100)
            take_profit = entry_price * (1 + self.config.take_profit_pct / 100)
        else:
            entry_price = base_price * (1 - slippage)
            stop_loss = entry_price * (1 + self.config.stop_loss_pct / 100)
            take_profit = entry_price * (1 - self.config.take_profit_pct / 100)
        
        return PatternSignal(
            signal_type='long' if direction == 'up' else 'short',
            pattern_name='1-2-3 Ross Hook',
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            thrust=thrust,
            confidence=min(thrust / 1.0, 1.0),
            metadata={
                'pattern_type': pattern['type'],
                'p1': pattern['p1'],
                'p2': pattern['p2'],
                'p3': pattern['p3'],
            }
        )
    
    def _try_ledge(self, records: List[dict], current_idx: int,
                   closes: List[float], opens: List[float],
                   highs: List[float], lows: List[float],
                   ht_closes: List[float] = None) -> Optional[PatternSignal]:
        """尝试Ledge旗杆信号"""
        
        ledge = self.find_ledge(closes, highs, lows, current_idx)
        if not ledge:
            return None
        
        direction = 'up' if ledge['type'] == 'bullish_ledge' else 'down'
        
        # RSI过滤
        pass_rsi, _ = self.check_rsi_filter(closes, direction)
        if not pass_rsi:
            return None
        
        # 多周期确认
        if ht_closes:
            pass_ht, _ = self.check_multi_timeframe_confirm(ht_closes, direction)
            if not pass_ht:
                return None
        
        # 成交量过滤
        current_volume = records[current_idx].get('qty', 0)
        if not self.check_volume(current_volume):
            return None
        
        # 成交率模拟
        if not self.check_fill():
            return None
        
        # 计算价格
        slippage = self.config.slippage_pct / 100
        base_price = opens[current_idx]
        
        if direction == 'up':
            entry_price = base_price * (1 + slippage)
            stop_loss = entry_price * (1 - self.config.stop_loss_pct / 100)
            take_profit = entry_price * (1 + self.config.take_profit_pct / 100)
        else:
            entry_price = base_price * (1 - slippage)
            stop_loss = entry_price * (1 + self.config.stop_loss_pct / 100)
            take_profit = entry_price * (1 - self.config.take_profit_pct / 100)
        
        return PatternSignal(
            signal_type='long',
            pattern_name='Bullish Ledge' if direction == 'up' else 'Bearish Ledge',
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            thrust=0.5,
            confidence=0.6,
            metadata=ledge
        )
    
    def _try_trading_range(self, records: List[dict], current_idx: int,
                           closes: List[float], opens: List[float],
                           highs: List[float], lows: List[float],
                           ht_closes: List[float] = None) -> Optional[PatternSignal]:
        """尝试Trading Range信号"""
        
        tr = self.find_trading_range(closes, highs, lows, current_idx)
        if not tr:
            return None
        
        # 判断突破方向
        current_price = closes[current_idx]
        
        if tr['position_pct'] > 0.9:  # 接近上轨，做空
            direction = 'down'
        elif tr['position_pct'] < 0.1:  # 接近下轨，做多
            direction = 'up'
        else:
            return None  # 中间位置不交易
        
        # RSI过滤
        pass_rsi, _ = self.check_rsi_filter(closes, direction)
        if not pass_rsi:
            return None
        
        # 多周期确认
        if ht_closes:
            pass_ht, _ = self.check_multi_timeframe_confirm(ht_closes, direction)
            if not pass_ht:
                return None
        if not pass_rsi:
            return None
        
        # 成交量过滤
        current_volume = records[current_idx].get('qty', 0)
        if not self.check_volume(current_volume):
            return None
        
        # 成交率模拟
        if not self.check_fill():
            return None
        
        # 计算价格
        slippage = self.config.slippage_pct / 100
        base_price = opens[current_idx]
        
        if direction == 'up':
            entry_price = base_price * (1 + slippage)
            stop_loss = entry_price * (1 - self.config.stop_loss_pct / 100)
            take_profit = entry_price * (1 + self.config.take_profit_pct / 100)
        else:
            entry_price = base_price * (1 - slippage)
            stop_loss = entry_price * (1 + self.config.stop_loss_pct / 100)
            take_profit = entry_price * (1 - self.config.take_profit_pct / 100)
        
        return PatternSignal(
            signal_type='long' if direction == 'up' else 'short',
            pattern_name='Trading Range Breakout',
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            thrust=tr['range_pct'],
            confidence=0.5,
            metadata=tr
        )


def create_signal_generator(config) -> SignalGenerator:
    """创建信号生成器"""
    return SignalGenerator(config)
