"""
风险管理模块

风险管理器 - 实现多种出场策略
- 固定止损
- 移动止损
- 分批止盈
- ATR止损
- 趋势过滤
"""

from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .position import Position

from dataclasses import dataclass


@dataclass
class ExitSignal:
    """出场信号"""
    should_exit: bool = False
    reason: str = ''
    exit_price: float = 0.0
    pnl_pct: float = 0.0
    metadata: dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class RiskManager:
    """风险管理器"""
    
    def __init__(self, config):
        self.config = config
        self.stop_loss_pct = config.stop_loss_pct
        self.take_profit_pct = config.take_profit_pct
        self.max_hold_bars = config.max_hold_bars
        
        # 移动止损
        self.enable_trailing_stop = getattr(config, 'enable_trailing_stop', False)
        self.trailing_stop_pct = getattr(config, 'trailing_stop_pct', 0)
        
        # 分批止盈
        self.enable_partial_tp = getattr(config, 'enable_partial_tp', False)
        self.partial_tp_pct = getattr(config, 'partial_tp_pct', 0)
        
        # ATR止损
        self.enable_atr_stop = getattr(config, 'enable_atr_stop', False)
        self.atr_period = getattr(config, 'atr_period', 14)
        self.atr_multiplier = getattr(config, 'atr_multiplier', 2.0)
    
    # ==================== 辅助函数 ====================
    
    def get_atr(self, highs: List[float], lows: List[float], closes: List[float], 
                idx: int, period: int = None) -> Optional[float]:
        """计算ATR（平均真实波幅）"""
        if period is None:
            period = self.atr_period
            
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
    
    def get_ema(self, prices: List[float], idx: int, period: int = 21) -> Optional[float]:
        """计算EMA"""
        if idx < period:
            return None
        
        # 简单EMA计算
        multiplier = 2 / (period + 1)
        ema = prices[idx - period + 1]
        
        for i in range(idx - period + 2, idx + 1):
            ema = (prices[i] - ema) * multiplier + ema
        
        return ema
    
    def get_trend_direction(self, prices: List[float], highs: List[float], 
                           lows: List[float], idx: int) -> str:
        """
        判断趋势方向
        返回: 'up', 'down', 'neutral'
        """
        if idx < 20:
            return 'neutral'
        
        # 方法1: 价格与EMA比较
        ema21 = self.get_ema(prices, idx, 21)
        if ema21:
            current_price = prices[idx]
            if current_price > ema21 * 1.01:
                return 'up'
            elif current_price < ema21 * 0.99:
                return 'down'
        
        # 方法2: 高点低点判断
        recent_highs = highs[max(0, idx-20):idx]
        recent_lows = lows[max(0, idx-20):idx]
        
        if len(recent_highs) >= 5:
            # 连续高点上升 = 上涨趋势
            up_count = sum(1 for i in range(1, len(recent_highs)) if recent_highs[i] > recent_highs[i-1])
            down_count = sum(1 for i in range(1, len(recent_lows)) if recent_lows[i] < recent_lows[i-1])
            
            if up_count >= 4:
                return 'up'
            elif down_count >= 4:
                return 'down'
        
        return 'neutral'
    
    # ==================== 出场检查 ====================
    
    def check_stop_loss(self, position: 'Position', current_price: float, 
                        current_high: float, current_low: float) -> ExitSignal:
        """检查固定止损"""
        if position.type == 'long':
            if current_low <= position.stop_loss:
                pnl_pct = (position.stop_loss - position.entry_price) / position.entry_price * 100
                return ExitSignal(
                    should_exit=True,
                    reason=f"止损 {abs(pnl_pct):.2f}%",
                    exit_price=position.stop_loss,
                    pnl_pct=pnl_pct,
                    metadata={'trigger_price': current_low, 'stop_price': position.stop_loss}
                )
        else:
            if current_high >= position.stop_loss:
                pnl_pct = (position.entry_price - position.stop_loss) / position.entry_price * 100
                return ExitSignal(
                    should_exit=True,
                    reason=f"止损 {abs(pnl_pct):.2f}%",
                    exit_price=position.stop_loss,
                    pnl_pct=pnl_pct,
                    metadata={'trigger_price': current_high, 'stop_price': position.stop_loss}
                )
        
        return ExitSignal()
    
    def check_atr_stop(self, position: 'Position', highs: List[float], 
                      lows: List[float], closes: List[float], idx: int) -> Optional[ExitSignal]:
        """
        检查ATR止损
        ATR止损 = 入场价 ± ATR * multiplier
        """
        if not self.enable_atr_stop:
            return None
        
        atr = self.get_atr(highs, lows, closes, idx, self.atr_period)
        if atr is None:
            return None
        
        # 计算ATR止损价
        if position.type == 'long':
            # 多头: 止损价 = 入场价 - ATR * multiplier
            atr_stop = position.entry_price - atr * self.atr_multiplier
            # 只有当ATR止损比固定止损更宽松时才使用
            fixed_stop = position.entry_price * (1 - self.stop_loss_pct / 100)
            if atr_stop > fixed_stop:  # ATR止损更宽松，不用
                return None
            
            if closes[idx] <= atr_stop:
                pnl_pct = (atr_stop - position.entry_price) / position.entry_price * 100
                return ExitSignal(
                    should_exit=True,
                    reason=f"ATR止损 {abs(pnl_pct):.2f}%",
                    exit_price=atr_stop,
                    pnl_pct=pnl_pct,
                    metadata={'atr': atr, 'atr_stop': atr_stop}
                )
        else:
            # 空头: 止损价 = 入场价 + ATR * multiplier
            atr_stop = position.entry_price + atr * self.atr_multiplier
            fixed_stop = position.entry_price * (1 + self.stop_loss_pct / 100)
            if atr_stop < fixed_stop:
                return None
            
            if closes[idx] >= atr_stop:
                pnl_pct = (position.entry_price - atr_stop) / position.entry_price * 100
                return ExitSignal(
                    should_exit=True,
                    reason=f"ATR止损 {abs(pnl_pct):.2f}%",
                    exit_price=atr_stop,
                    pnl_pct=pnl_pct,
                    metadata={'atr': atr, 'atr_stop': atr_stop}
                )
        
        return None
    
    def check_take_profit(self, position: 'Position', current_price: float) -> ExitSignal:
        """检查固定止盈"""
        if position.type == 'long':
            if current_price >= position.take_profit:
                pnl_pct = (position.take_profit - position.entry_price) / position.entry_price * 100
                return ExitSignal(
                    should_exit=True,
                    reason=f"止盈 {pnl_pct:.2f}%",
                    exit_price=position.take_profit,
                    pnl_pct=pnl_pct,
                )
        else:
            if current_price <= position.take_profit:
                pnl_pct = (position.entry_price - position.take_profit) / position.entry_price * 100
                return ExitSignal(
                    should_exit=True,
                    reason=f"止盈 {pnl_pct:.2f}%",
                    exit_price=position.take_profit,
                    pnl_pct=pnl_pct,
                )
        
        return ExitSignal()
    
    def check_timeout(self, position: 'Position') -> ExitSignal:
        """检查超时"""
        if position.bars >= self.max_hold_bars:
            return ExitSignal(
                should_exit=True,
                reason=f"超时 {position.bars}根",
                exit_price=0,
                pnl_pct=0,
            )
        return ExitSignal()
    
    def check_trailing_stop(self, position: 'Position', current_price: float) -> ExitSignal:
        """检查移动止损"""
        if not self.enable_trailing_stop or not self.trailing_stop_pct:
            return ExitSignal()
        
        # 更新最高/最低价
        if position.type == 'long':
            if current_price > position.highest_price:
                position.highest_price = current_price
            
            # 检查是否达到触发条件
            profit_pct = (position.highest_price - position.entry_price) / position.entry_price * 100
            if profit_pct >= self.trailing_stop_pct:
                # 移动止损提高到盈亏平衡点
                if position.trailing_stop is None or position.trailing_stop < position.entry_price:
                    position.trailing_stop = position.entry_price
                
                # 检查是否触发（价格回落触及移动止损）
                if position.trailing_stop and current_price <= position.trailing_stop:
                    pnl_pct = (position.trailing_stop - position.entry_price) / position.entry_price * 100
                    return ExitSignal(
                        should_exit=True,
                        reason=f"移动止损 {pnl_pct:.2f}%",
                        exit_price=position.trailing_stop,
                        pnl_pct=pnl_pct,
                    )
        else:
            if position.lowest_price == 0 or current_price < position.lowest_price:
                position.lowest_price = current_price
            
            profit_pct = (position.entry_price - position.lowest_price) / position.entry_price * 100
            if profit_pct >= self.trailing_stop_pct:
                if position.trailing_stop is None or position.trailing_stop > position.entry_price:
                    position.trailing_stop = position.entry_price
                
                if position.trailing_stop and current_price >= position.trailing_stop:
                    pnl_pct = (position.entry_price - position.trailing_stop) / position.entry_price * 100
                    return ExitSignal(
                        should_exit=True,
                        reason=f"移动止损 {pnl_pct:.2f}%",
                        exit_price=position.trailing_stop,
                        pnl_pct=pnl_pct,
                    )
        
        return ExitSignal()
    
    def check_partial_take_profit(self, position: 'Position', current_price: float) -> Optional[ExitSignal]:
        """检查分批止盈（50%仓位）"""
        if not self.enable_partial_tp or not self.partial_tp_pct or position.partial_tp_triggered:
            return None
        
        if position.type == 'long':
            profit_pct = (current_price - position.entry_price) / position.entry_price * 100
            if profit_pct >= self.partial_tp_pct:
                position.partial_tp_triggered = True
                return ExitSignal(
                    should_exit=True,
                    reason=f"部分止盈 {profit_pct:.2f}%",
                    exit_price=current_price,
                    pnl_pct=profit_pct,
                    metadata={'partial': True, 'remaining_pct': 50}
                )
        else:
            profit_pct = (position.entry_price - current_price) / position.entry_price * 100
            if profit_pct >= self.partial_tp_pct:
                position.partial_tp_triggered = True
                return ExitSignal(
                    should_exit=True,
                    reason=f"部分止盈 {profit_pct:.2f}%",
                    exit_price=current_price,
                    pnl_pct=profit_pct,
                    metadata={'partial': True, 'remaining_pct': 50}
                )
        
        return None
    
    # ==================== 趋势过滤 ====================
    
    def check_trend_filter(self, prices: List[float], highs: List[float], 
                          lows: List[float], idx: int, trade_direction: str) -> tuple:
        """
        趋势过滤检查（由趋势周期控制：有值=开启，无值=关闭）
        返回: (是否允许交易, 原因)
        """
        # 趋势周期有值才开启趋势过滤
        if not getattr(self.config, 'higher_timeframe', ''):
            return True, ""
        
        trend = self.get_trend_direction(prices, highs, lows, idx)
        
        if trend == 'neutral':
            return True, ""  # 中性趋势不过滤
        
        # 多头交易只在上涨趋势中允许
        if trade_direction == 'long' and trend == 'down':
            return False, f"趋势向下({trend})，禁止做多"
        
        # 空头交易只在下跌趋势中允许
        if trade_direction == 'short' and trend == 'up':
            return False, f"趋势向上({trend})，禁止做空"
        
        return True, ""
    
    # ==================== 综合出场 ====================
    
    def check_exit(self, position: 'Position', current_price: float, 
                   current_high: float, current_low: float,
                   highs: List[float] = None, lows: List[float] = None, 
                   closes: List[float] = None, idx: int = None) -> ExitSignal:
        """
        综合出场检查
        
        Args:
            position: 持仓
            current_price: 当前价格
            current_high: 当前最高价
            current_low: 当前最低价
            highs: 最高价列表（用于ATR计算）
            lows: 最低价列表（用于ATR计算）
            closes: 收盘价列表（用于ATR计算）
            idx: 当前索引（用于ATR计算）
        """
        # 1. 固定止损
        exit_signal = self.check_stop_loss(position, current_price, current_high, current_low)
        if exit_signal.should_exit:
            return exit_signal
        
        # 2. ATR止损
        if all([highs, lows, closes, idx is not None]):
            exit_signal = self.check_atr_stop(position, highs, lows, closes, idx)
            if exit_signal and exit_signal.should_exit:
                return exit_signal
        
        # 3. 移动止损
        exit_signal = self.check_trailing_stop(position, current_price)
        if exit_signal.should_exit:
            return exit_signal
        
        # 4. 固定止盈
        exit_signal = self.check_take_profit(position, current_price)
        if exit_signal.should_exit:
            return exit_signal
        
        # 5. 分批止盈
        exit_signal = self.check_partial_take_profit(position, current_price)
        if exit_signal and exit_signal.should_exit:
            return exit_signal
        
        # 6. 超时
        exit_signal = self.check_timeout(position)
        if exit_signal.should_exit:
            return exit_signal
        
        return ExitSignal()
    
    # ==================== 仓位计算 ====================
    
    def calculate_position_size(self, balance: float) -> float:
        """计算仓位大小（以损定仓）"""
        if self.config.use_position_size_mode:
            return getattr(self.config, 'position_size', 100)
        
        raw_position = (balance * self.config.risk_pct / 100) / (self.stop_loss_pct / 100)
        return min(raw_position, self.config.max_position)
    
    def calculate_pnl(self, position: 'Position', exit_price: float) -> float:
        """计算盈亏"""
        if position.type == 'long':
            pnl_pct = (exit_price - position.entry_price) / position.entry_price * 100
        else:
            pnl_pct = (position.entry_price - exit_price) / position.entry_price * 100
        return pnl_pct / 100 * position.position_size
    
    def calculate_commission(self, position_size: float, entry: bool = True, exit: bool = True) -> float:
        """计算手续费"""
        rate = self.config.commission_rate / 100
        commission = 0
        if entry:
            commission += position_size * rate
        if exit:
            commission += position_size * rate
        return commission


def create_risk_manager(config) -> RiskManager:
    """创建风险管理器"""
    return RiskManager(config)
