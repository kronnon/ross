"""
风险管理模块 v5

v5 更新：
- 新增每日最大亏损检查：max_daily_loss
"""

from typing import List, Tuple
from dataclasses import dataclass


@dataclass
class ExitSignal:
    """出场信号"""
    should_exit: bool       # 是否出场
    reason: str = ""        # 出场原因
    exit_price: float = 0.0 # 出场价格
    partial: bool = False   # 是否部分止盈


class RiskManager:
    """风险管理器 - v5 增强版"""
    
    def __init__(self, config):
        self.config = config
        
        # 止损止盈
        self.stop_loss_pct = config.stop_loss_pct
        self.take_profit_pct = config.take_profit_pct
        self.max_hold_bars = config.max_hold_bars
        
        # 移动止损
        self.enable_trailing_stop = getattr(config, 'enable_trailing_stop', False)
        self.trailing_stop_pct = getattr(config, 'trailing_stop_pct', 0.0)
        
        # 分批止盈
        self.enable_partial_tp = getattr(config, 'enable_partial_tp', False)
        self.partial_tp_pct = getattr(config, 'partial_tp_pct', 0.0)
        
        # ATR止损
        self.enable_atr_stop = getattr(config, 'enable_atr_stop', False)
        self.atr_period = getattr(config, 'atr_period', 14)
        self.atr_multiplier = getattr(config, 'atr_multiplier', 2.0)
    
    def check_exit(self, position, current_price: float, current_high: float,
                   current_low: float, highs: List[float] = None,
                   lows: List[float] = None, closes: List[float] = None,
                   idx: int = None) -> ExitSignal:
        """
        综合出场检查
        
        检查顺序：
        1. 止损（包括形态破坏止损）
        2. 止盈
        3. 超时平仓
        4. 移动止损
        5. 分批止盈
        6. ATR止损
        """
        
        # 1. 止损检查
        if position.type == 'long':
            # 常规止损
            if current_low <= position.stop_loss:
                return ExitSignal(
                    should_exit=True,
                    reason="止损",
                    exit_price=position.stop_loss
                )
        else:
            # 常规止损
            if current_high >= position.stop_loss:
                return ExitSignal(
                    should_exit=True,
                    reason="止损",
                    exit_price=position.stop_loss
                )
        
        # 2. 止盈检查
        if position.type == 'long':
            if current_high >= position.take_profit:
                return ExitSignal(
                    should_exit=True,
                    reason="止盈",
                    exit_price=position.take_profit
                )
        else:
            if current_low <= position.take_profit:
                return ExitSignal(
                    should_exit=True,
                    reason="止盈",
                    exit_price=position.take_profit
                )
        
        # 3. 超时平仓
        if position.bars >= self.max_hold_bars:
            return ExitSignal(
                should_exit=True,
                reason="超时平仓",
                exit_price=current_price
            )
        
        # 4. 移动止损
        if self.enable_trailing_stop and self.trailing_stop_pct > 0:
            trailing_signal = self._check_trailing_stop(position, current_price)
            if trailing_signal.should_exit:
                return trailing_signal
        
        # 5. 分批止盈
        if self.enable_partial_tp and self.partial_tp_pct > 0:
            partial_signal = self._check_partial_tp(position, current_price)
            if partial_signal.should_exit:
                return partial_signal
        
        # 6. ATR止损
        if self.enable_atr_stop and highs and lows and closes and idx is not None:
            atr_signal = self._check_atr_stop(position, current_price, highs, lows, closes, idx)
            if atr_signal.should_exit:
                return atr_signal
        
        return ExitSignal(should_exit=False)
    
    def _check_trailing_stop(self, position, current_price: float) -> ExitSignal:
        """检查移动止损"""
        if position.type == 'long':
            # 多头：盈利达到阈值后，用最高价的一定比例作为止损
            if position.highest_price > position.entry_price * (1 + self.trailing_stop_pct / 100):
                trailing_stop = position.highest_price * (1 - self.trailing_stop_pct / 100)
                if current_price <= trailing_stop:
                    return ExitSignal(
                        should_exit=True,
                        reason="移动止损",
                        exit_price=current_price
                    )
        else:
            # 空头：盈利达到阈值后，用最低价的一定比例作为止损
            if position.lowest_price < position.entry_price * (1 - self.trailing_stop_pct / 100):
                trailing_stop = position.lowest_price * (1 + self.trailing_stop_pct / 100)
                if current_price >= trailing_stop:
                    return ExitSignal(
                        should_exit=True,
                        reason="移动止损",
                        exit_price=current_price
                    )
        
        return ExitSignal(should_exit=False)
    
    def _check_partial_tp(self, position, current_price: float) -> ExitSignal:
        """检查分批止盈"""
        if position.partial_closed:
            return ExitSignal(should_exit=False)
        
        if position.type == 'long':
            profit_pct = (current_price - position.entry_price) / position.entry_price * 100
        else:
            profit_pct = (position.entry_price - current_price) / position.entry_price * 100
        
        if profit_pct >= self.partial_tp_pct:
            return ExitSignal(
                should_exit=True,
                reason="部分止盈",
                exit_price=current_price,
                partial=True
            )
        
        return ExitSignal(should_exit=False)
    
    def _check_atr_stop(self, position, current_price: float,
                        highs: List[float], lows: List[float],
                        closes: List[float], idx: int) -> ExitSignal:
        """检查ATR止损"""
        if idx < self.atr_period:
            return ExitSignal(should_exit=False)
        
        # 计算ATR
        trs = []
        for i in range(idx - self.atr_period + 1, idx + 1):
            if i == 0:
                continue
            high_low = highs[i] - lows[i]
            high_close = abs(highs[i] - closes[i-1])
            low_close = abs(lows[i] - closes[i-1])
            tr = max(high_low, high_close, low_close)
            trs.append(tr)
        
        if not trs:
            return ExitSignal(should_exit=False)
        
        atr = sum(trs) / len(trs)
        
        # ATR止损逻辑
        if position.type == 'long':
            atr_stop = position.entry_price - atr * self.atr_multiplier
            if current_price <= atr_stop:
                return ExitSignal(
                    should_exit=True,
                    reason="ATR止损",
                    exit_price=current_price
                )
        else:
            atr_stop = position.entry_price + atr * self.atr_multiplier
            if current_price >= atr_stop:
                return ExitSignal(
                    should_exit=True,
                    reason="ATR止损",
                    exit_price=current_price
                )
        
        return ExitSignal(should_exit=False)
    
    def check_daily_loss_limit(self, daily_pnl: float) -> Tuple[bool, str]:
        """
        v5: 检查每日最大亏损
        
        Args:
            daily_pnl: 当日累计盈亏
        
        Returns:
            (是否超过限制, 原因)
        """
        max_daily_loss = getattr(self.config, 'max_daily_loss', 50.0)
        
        if daily_pnl <= -max_daily_loss:
            return True, f"当日亏损{abs(daily_pnl):.2f}USDT已达上限{max_daily_loss}USDT"
        
        return False, ""
    
    def update_stop_loss(self, position, new_stop: float) -> bool:
        """
        更新止损价（用于移动止损）
        
        Returns:
            是否更新成功
        """
        if position.type == 'long':
            # 多头：只能上移止损
            if new_stop > position.stop_loss:
                position.stop_loss = new_stop
                return True
        else:
            # 空头：只能下移止损
            if new_stop < position.stop_loss:
                position.stop_loss = new_stop
                return True
        
        return False


def create_risk_manager(config) -> RiskManager:
    """创建风险管理器"""
    return RiskManager(config)
