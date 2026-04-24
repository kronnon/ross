"""
仓位管理模块 v5

v5 更新：
- 以损定仓支持 fixed_loss 和 risk_pct 两种模式
- 新增总仓位上限检查：max_total_position
- 新增固定仓位模式：use_position_size_mode + position_size
"""

from typing import List, Optional, Dict
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Position:
    """持仓信息"""
    type: str                    # 'long' or 'short'
    entry_price: float           # 入场价格
    entry_time: int              # 入场时间戳（毫秒）
    entry_idx: int               # 入场K线索引
    position_size: float         # 仓位金额（USDT）
    stop_loss: float             # 止损价
    take_profit: float           # 止盈价
    entry_signal: str = ""       # 入场信号类型
    entry_pattern: str = ""      # 入场形态
    thrust: float = 0.0          # 突破幅度
    bars: int = 0                # 持仓K线数
    highest_price: float = 0.0   # 持仓期间最高价（用于移动止损）
    lowest_price: float = 0.0    # 持仓期间最低价
    atr: float = 0.0             # 入场时ATR
    partial_closed: bool = False # 是否已部分止盈
    metadata: Dict = field(default_factory=dict)  # 额外信息
    
    def update_bars(self):
        """更新持仓K线数"""
        self.bars += 1
    
    def update_high_low(self, current_price: float):
        """更新持仓期间最高/最低价"""
        if self.highest_price == 0:
            self.highest_price = current_price
            self.lowest_price = current_price
        else:
            self.highest_price = max(self.highest_price, current_price)
            self.lowest_price = min(self.lowest_price, current_price)


@dataclass
class Trade:
    """交易记录"""
    entry_time_str: str          # 入场时间
    entry_price: float           # 入场价格
    position: str                # 'long' or 'short'
    exit_time_str: str           # 出场时间
    exit_price: float            # 出场价格
    hold_bars: int               # 持仓K线数
    position_size: float         # 仓位金额
    entry_signal: str            # 入场信号
    entry_pattern: str           # 入场形态
    thrust: float                # 突破幅度
    exit_reason: str             # 出场原因
    exit_logic: str = ""         # 出场逻辑详情
    profit_usd: float = 0.0      # 盈亏金额
    pnl_pct: float = 0.0         # 盈亏百分比
    commission: float = 0.0      # 手续费
    balance_after: float = 0.0   # 交易后余额
    concurrent_positions: int = 1 # 同时持仓数
    stop_loss: float = 0.0       # 计划止损价
    take_profit: float = 0.0     # 计划止盈价


class PositionManager:
    """仓位管理器 - v5 增强版"""
    
    def __init__(self, config, risk_manager=None):
        self.config = config
        self.risk_manager = risk_manager
        
        # 状态
        self.positions: List[Position] = []
        self.trades: List[Trade] = []
        self.balance = config.initial_balance
        self.initial_balance = config.initial_balance
        
        # v5: 每日亏损追踪
        self.daily_pnl: float = 0.0
        self.last_reset_day: str = ""
    
    def calculate_position_size(self, entry_price: float, stop_loss: float) -> float:
        """
        计算仓位大小

        三种模式（优先级依次降低）：
        1. 固定仓位模式（use_position_size_mode=True）：直接用 position_size
        2. 固定亏损模式（fixed_loss > 0）：仓位 = fixed_loss / 止损%
        3. 百分比模式（fixed_loss = 0）：仓位 = 余额 × risk_pct% / 止损%
        """
        if getattr(self.config, 'use_position_size_mode', False):
            return getattr(self.config, 'position_size', 100.0)

        if entry_price <= 0:
            return 0

        stop_loss_pct = abs(entry_price - stop_loss) / entry_price
        if stop_loss_pct <= 0:
            return 0

        fixed_loss = getattr(self.config, 'fixed_loss', 0)
        if fixed_loss > 0:
            # 固定亏损模式
            position_size = fixed_loss / stop_loss_pct
        else:
            # 百分比模式
            risk_pct = getattr(self.config, 'risk_pct', 2.0)
            position_size = self.balance * (risk_pct / 100) / stop_loss_pct
        
        # 应用杠杆
        leverage = self.config.leverage
        position_size *= leverage
        
        # 限制最大仓位
        max_position = self.config.max_position
        position_size = min(position_size, max_position)
        
        # v5: 检查总仓位上限
        max_total = getattr(self.config, 'max_total_position', 1000.0)
        current_total = self.get_total_position_size()
        remaining = max_total - current_total
        position_size = min(position_size, remaining)
        
        return max(position_size, 0)
    
    def get_total_position_size(self) -> float:
        """获取当前总仓位金额"""
        return sum(p.position_size for p in self.positions)
    
    def can_open_position(self, side: str = None) -> bool:
        """检查是否可以开仓
        
        Args:
            side: 新仓位方向 ('long' or 'short')，用于判断是否允许同向加仓
        """
        # v5: 检查总仓位上限
        max_total = getattr(self.config, 'max_total_position', 1000.0)
        if self.get_total_position_size() >= max_total:
            return False
        
        # v5: 检查每日最大亏损
        max_daily_loss = getattr(self.config, 'max_daily_loss', 50.0)
        if self.daily_pnl <= -max_daily_loss:
            return False
        
        # v5: 允许同向加仓（如果有持仓且方向相同，可以加仓）
        # 如果有持仓但方向不同，需要先平反向仓位
        if side and self.get_position_count() > 0:
            for pos in self.positions:
                if pos.type != side:
                    # 有反向持仓，需要先平仓
                    # 但这不影响开仓判断，因为会在入场时自动平反向仓位
                    pass
        
        return True
    
    def open_position(self, signal, current_time: int, current_idx: int) -> Optional[Position]:
        """
        开仓

        Args:
            signal: 信号对象（PatternSignal）
            current_time: 当前时间戳
            current_idx: 当前K线索引

        Returns:
            Position 或 None
        """
        if not self.can_open_position():
            return None
        
        # 计算滑点后的实际入场价
        slippage = self.config.slippage_pct / 100
        if signal.side == 'long':
            # 做多：向上滑点
            actual_entry_price = signal.entry_price * (1 + slippage)
        else:
            # 做空：向下滑点
            actual_entry_price = signal.entry_price * (1 - slippage)
        
        # 基于实际入场价重新计算止损止盈
        if signal.side == 'long':
            actual_stop_loss = actual_entry_price * (1 - self.config.stop_loss_pct / 100)
            actual_take_profit = actual_entry_price * (1 + self.config.take_profit_pct / 100)
        else:
            actual_stop_loss = actual_entry_price * (1 + self.config.stop_loss_pct / 100)
            actual_take_profit = actual_entry_price * (1 - self.config.take_profit_pct / 100)
        
        # 计算仓位（使用实际入场价和实际止损价）
        position_size = self.calculate_position_size(actual_entry_price, actual_stop_loss)

        if position_size <= 0:
            return None

        # 检查余额
        if position_size > self.balance:
            position_size = self.balance

        # 余额不足，不开仓
        if position_size <= 0:
            return None
        
        # 创建持仓
        position = Position(
            type=signal.side,
            entry_price=actual_entry_price,
            entry_time=current_time,
            entry_idx=current_idx,
            position_size=position_size,
            stop_loss=actual_stop_loss,
            take_profit=actual_take_profit,
            entry_signal=signal.side,
            entry_pattern=signal.pattern_name,
            thrust=signal.thrust,
            bars=0,
            highest_price=actual_entry_price,
            lowest_price=actual_entry_price,

            metadata=signal.metadata or {},
        )
        
        self.positions.append(position)
        self.balance -= position_size
        
        return position
    
    def close_position(self, position: Position, exit_price: float, 
                       exit_reason: str, exit_logic: str = "",
                       exit_time_str: str = "") -> Optional[Trade]:
        """平仓"""
        if position not in self.positions:
            return None
        
        # 计算盈亏
        if position.type == 'long':
            pnl_pct = (exit_price - position.entry_price) / position.entry_price * 100
            profit_usd = position.position_size * pnl_pct / 100
        else:
            pnl_pct = (position.entry_price - exit_price) / position.entry_price * 100
            profit_usd = position.position_size * pnl_pct / 100
        
        # 双边手续费（开仓 + 平仓）
        commission = position.position_size * self.config.commission_rate / 100 * 2
        profit_usd -= commission
        
        # 更新余额
        self.balance += position.position_size + profit_usd
        
        # v5: 更新每日亏损
        self.daily_pnl += profit_usd
        
        # 创建交易记录
        trade = Trade(
            entry_time_str=datetime.fromtimestamp(position.entry_time/1000).strftime('%Y-%m-%d %H:%M'),
            entry_price=position.entry_price,
            position=position.type,
            exit_time_str=exit_time_str or datetime.now().strftime('%Y-%m-%d %H:%M'),
            exit_price=exit_price,
            hold_bars=position.bars,
            position_size=position.position_size,
            entry_signal=position.entry_signal,
            entry_pattern=position.entry_pattern,
            thrust=position.thrust,
            exit_reason=exit_reason,
            exit_logic=exit_logic,
            profit_usd=profit_usd,
            pnl_pct=pnl_pct,
            commission=commission,
            balance_after=self.balance,
            concurrent_positions=len(self.positions),
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
        )
        
        self.trades.append(trade)
        self.positions.remove(position)
        
        return trade
    
    def close_all_opposite_direction(self, side: str, current_price: float,
                                      slippage: float, current_time: int, current_idx: int,
                                      exit_time_str: str = ""):
        """平掉所有反向持仓"""
        to_close = []
        
        for pos in self.positions:
            if pos.type != side:
                if pos.type == 'long':
                    exit_price = current_price * (1 - slippage)
                else:
                    exit_price = current_price * (1 + slippage)
                
                self.close_position(pos, exit_price, "反向信号", "收到反向信号平仓", exit_time_str)
                to_close.append(pos)
        
        return to_close
    
    def update_positions(self, current_price: float):
        """更新所有持仓状态"""
        for pos in self.positions:
            pos.update_bars()
            pos.update_high_low(current_price)
    
    def get_position_count(self) -> int:
        """获取当前持仓数量"""
        return len(self.positions)
    
    def get_stats(self) -> Dict:
        """获取交易统计"""
        if not self.trades:
            return {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'final_balance': self.balance,
                'daily_pnl': self.daily_pnl,
            }
        
        wins = sum(1 for t in self.trades if t.profit_usd > 0)
        losses = sum(1 for t in self.trades if t.profit_usd <= 0)
        total_pnl = sum(t.profit_usd for t in self.trades)
        
        return {
            'total_trades': len(self.trades),
            'wins': wins,
            'losses': losses,
            'win_rate': wins / len(self.trades) * 100 if self.trades else 0,
            'total_pnl': total_pnl,
            'final_balance': self.balance,
            'daily_pnl': self.daily_pnl,
        }
    
    def get_exit_reasons(self) -> Dict[str, int]:
        """获取出场原因统计"""
        reasons = {}
        for t in self.trades:
            reason = t.exit_reason
            reasons[reason] = reasons.get(reason, 0) + 1
        return reasons
    
    def reset_daily_pnl(self):
        """重置每日亏损（每天开始时调用）"""
        self.daily_pnl = 0.0
        self.last_reset_day = datetime.now().strftime('%Y-%m-%d')
    
    def check_and_reset_daily(self):
        """检查并重置每日亏损"""
        current_day = datetime.now().strftime('%Y-%m-%d')
        if current_day != self.last_reset_day:
            self.reset_daily_pnl()


def create_position_manager(config, risk_manager=None) -> PositionManager:
    """创建仓位管理器"""
    return PositionManager(config, risk_manager)
