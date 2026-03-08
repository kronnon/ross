"""
仓位管理模块
"""

from typing import List, Optional, Dict
from dataclasses import dataclass, field
from datetime import datetime
import uuid


@dataclass
class Position:
    """持仓"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: str = 'long'           # 'long' or 'short'
    entry_price: float = 0.0     # 入场价格（含滑点）
    entry_time: int = 0          # 入场时间（毫秒）
    entry_idx: int = 0           # 入场K线索引
    position_size: float = 0.0   # 仓位大小（USDT）
    
    # 止损止盈
    stop_loss: float = 0.0       # 止损价格
    take_profit: float = 0.0    # 止盈价格
    
    # 状态
    bars: int = 0                # 持仓K线数
    entry_signal: str = ''       # 入场信号
    entry_pattern: str = ''      # 入场形态
    thrust: float = 0.0          # 突破幅度
    
    # 扩展
    slippage: float = 0.0       # 滑点
    highest_price: float = 0.0   # 持仓期间最高价
    lowest_price: float = 0.0   # 持仓期间最低价
    
    # 分批止盈
    partial_tp_triggered: bool = False  # 是否已触发部分止盈
    
    # 移动止损
    trailing_stop: Optional[float] = None  # 移动止损价格
    
    def update_bars(self):
        """更新持仓K线数"""
        self.bars += 1
    
    def update_high_low(self, current_price: float):
        """更新最高/最低价"""
        if self.type == 'long':
            if current_price > self.highest_price:
                self.highest_price = current_price
        else:
            if self.lowest_price == 0 or current_price < self.lowest_price:
                self.lowest_price = current_price


@dataclass
class Trade:
    """交易记录"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    
    # 入场
    entry_time_str: str = ''
    entry_price: float = 0.0
    position: str = 'long'
    
    # 出场
    exit_time_str: str = ''
    exit_price: float = 0.0
    
    # 持仓
    hold_bars: int = 0
    concurrent_positions: int = 1
    
    # 仓位
    position_size: float = 0.0
    
    # 信号
    entry_signal: str = ''
    entry_pattern: str = ''
    thrust: float = 0.0
    
    # 出场
    exit_reason: str = ''
    exit_logic: str = ''
    
    # 费用
    commission: float = 0.0
    
    # 盈亏
    profit_usd: float = 0.0
    pnl_pct: float = 0.0
    balance_after: float = 0.0


class PositionManager:
    """仓位管理器"""
    
    def __init__(self, config, risk_manager):
        self.config = config
        self.risk_manager = risk_manager
        self.max_concurrent = config.max_concurrent_positions
        self.positions: List[Position] = []
        self.balance: float = config.initial_balance
        self.trades: List[Trade] = []
        
        # 统计
        self.wins: int = 0
        self.losses: int = 0
    
    def can_open_position(self) -> bool:
        """是否可以开仓"""
        return len(self.positions) < self.max_concurrent
    
    def get_position_count(self) -> int:
        """获取当前持仓数"""
        return len(self.positions)
    
    def open_position(self, signal, time: int, idx: int, slippage: float) -> Optional[Position]:
        """开仓"""
        if not self.can_open_position():
            return None
        
        # 计算仓位大小
        position_size = self.risk_manager.calculate_position_size(self.balance)
        
        # 计算滑点后的入场价
        if signal.signal_type == 'long':
            entry_price = signal.entry_price
            stop_loss = entry_price * (1 - self.config.stop_loss_pct / 100)
            take_profit = entry_price * (1 + self.config.take_profit_pct / 100)
        else:
            entry_price = signal.entry_price
            stop_loss = entry_price * (1 + self.config.stop_loss_pct / 100)
            take_profit = entry_price * (1 - self.config.take_profit_pct / 100)
        
        # 扣除手续费
        commission = self.risk_manager.calculate_commission(position_size, entry=True, exit=False)
        self.balance -= commission
        
        position = Position(
            type=signal.signal_type,
            entry_price=entry_price,
            entry_time=time,
            entry_idx=idx,
            position_size=position_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_signal=signal.signal_type,
            entry_pattern=signal.pattern_name,
            thrust=signal.thrust,
            slippage=slippage,
            highest_price=entry_price,
            lowest_price=entry_price,
        )
        
        self.positions.append(position)
        return position
    
    def close_position(self, position: Position, exit_price: float, 
                       exit_reason: str, exit_logic: str = '',
                       entry_time_str: str = '', exit_time_str: str = '') -> Trade:
        """平仓"""
        # 计算盈亏
        if position.type == 'long':
            pnl_pct = (exit_price - position.entry_price) / position.entry_price * 100
        else:
            pnl_pct = (position.entry_price - exit_price) / position.entry_price * 100
        
        # 计算手续费
        commission = self.risk_manager.calculate_commission(
            position.position_size, entry=False, exit=True
        )
        
        # 计算实际盈亏
        profit = pnl_pct / 100 * position.position_size - commission
        self.balance += profit
        
        # 更新统计
        if profit > 0:
            self.wins += 1
        else:
            self.losses += 1
        
        # 记录交易
        trade = Trade(
            entry_time_str=entry_time_str or datetime.fromtimestamp(
                position.entry_time / 1000
            ).strftime('%Y-%m-%d %H:%M') if position.entry_time else '',
            entry_price=position.entry_price,
            position=position.type,
            exit_time_str=exit_time_str or '',
            exit_price=exit_price,
            hold_bars=position.bars,
            concurrent_positions=1,  # 入场时为1
            position_size=position.position_size,
            entry_signal=position.entry_signal,
            entry_pattern=position.entry_pattern,
            thrust=position.thrust,
            exit_reason=exit_reason,
            exit_logic=exit_logic,
            commission=commission,
            profit_usd=profit,
            pnl_pct=pnl_pct,
            balance_after=self.balance,
        )
        
        self.trades.append(trade)
        
        # 移除持仓
        self.positions.remove(position)
        
        return trade
    
    def close_all_opposite_direction(self, new_type: str, current_price: float, 
                                      slippage: float, time: int, idx: int,
                                      time_str: str = '') -> List[Trade]:
        """平掉所有相反方向的持仓"""
        closed_trades = []
        
        # 需要平仓的持仓
        to_close = [p for p in self.positions if p.type != new_type]
        
        for pos in to_close:
            # 计算出场价（含滑点）
            if new_type == 'long':
                exit_price = current_price * (1 - slippage)
            else:
                exit_price = current_price * (1 + slippage)
            
            trade = self.close_position(
                pos, exit_price, '反向开仓',
                f"发现相反方向信号，平仓后反向开仓",
                exit_time_str=time_str
            )
            closed_trades.append(trade)
        
        return closed_trades
    
    def update_positions(self, current_price: float):
        """更新所有持仓状态"""
        for pos in self.positions:
            pos.update_bars()
            pos.update_high_low(current_price)
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        total = len(self.trades)
        if total == 0:
            return {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'avg_pnl': 0,
            }
        
        wins = [t for t in self.trades if t.profit_usd > 0]
        losses = [t for t in self.trades if t.profit_usd <= 0]
        
        return {
            'total_trades': total,
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': len(wins) / total * 100,
            'total_pnl': sum(t.profit_usd for t in self.trades),
            'avg_pnl': sum(t.profit_usd for t in self.trades) / total,
            'max_profit': max((t.profit_usd for t in self.trades), default=0),
            'max_loss': min((t.profit_usd for t in self.trades), default=0),
            'final_balance': self.balance,
        }
    
    def get_exit_reasons(self) -> Dict[str, int]:
        """获取出场原因统计"""
        reasons = {}
        for t in self.trades:
            reason = t.exit_reason
            reasons[reason] = reasons.get(reason, 0) + 1
        return reasons


def create_position_manager(config, risk_manager) -> PositionManager:
    """创建仓位管理器"""
    return PositionManager(config, risk_manager)
