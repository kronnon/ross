#!/usr/bin/env python3
"""
实盘模拟交易 v5 - Binance Demo Mode

功能：
- WebSocket 实时获取 K 线
- 复用 v5 策略信号
- Demo Mode 模拟下单
- 持仓管理
- 交易记录输出

v5 更新：
- 支持 fixed_loss 以损定仓
- 支持总仓位上限检查
- 支持形态破坏止损
- 支持每日最大亏损
- 支持 KDJ/BOLL/EMA 过滤器
"""

import asyncio
import ccxt
from datetime import datetime
from typing import List, Optional, Dict
import os
import sys

# 添加 strategies 到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from signals import SignalGenerator, PatternSignal
from config import StrategyConfig
from position import Position, Trade, PositionManager
from risk import RiskManager


class LiveSimulator:
    """实盘模拟交易 - v5 增强版"""
    
    def __init__(self, config: Dict):
        # 加载配置
        self.strategy_config = StrategyConfig.from_dict(config)
        
        # 初始化 CCXT - Demo Mode
        self.exchange = ccxt.binance({
            'apiKey': config['demo_api_key'],
            'secret': config['demo_api_secret'],
            'enableRateLimit': True,
            'urls': {
                'api': {
                    'public': 'https://demo-api.binance.com/api/v3',
                    'private': 'https://demo-api.binance.com/api/v3',
                    'web': 'https://demo.binance.com',
                },
            },
            'options': {
                'defaultType': 'spot',
            }
        })
        
        self.symbol = config.get('symbol', 'BTC/USDT')
        self.interval = config.get('interval', '5m')
        self.initial_balance = config.get('initial_balance', 10000)
        
        # 数据存储
        self.ohlcv_data: List[List] = []  # [timestamp, open, high, low, close, volume]
        self.positions: List[Position] = []
        self.trades: List[Trade] = []
        self.balance = self.initial_balance
        
        # 信号生成器
        self.signal_generator = SignalGenerator(self.strategy_config)
        
        # 风险管理器
        self.risk_manager = RiskManager(self.strategy_config)
        
        # 仓位管理器
        self.position_manager = PositionManager(self.strategy_config, self.risk_manager)
        
        # 状态
        self.last_kline_time = 0
        self.is_running = False
        
        # v5: 每日亏损追踪
        self.current_day = ""
        
        # 输出目录
        self.output_dir = config.get('output_dir', 'outputs')
        os.makedirs(self.output_dir, exist_ok=True)
    
    async def initialize(self):
        """初始化：获取历史 K 线"""
        print(f"📊 初始化：获取 {self.symbol} 历史 K 线...")
        
        ohlcv = await self.exchange.fetch_ohlcv(
            self.symbol, 
            self.interval, 
            limit=500
        )
        
        self.ohlcv_data = ohlcv
        print(f"✅ 获取 {len(ohlcv)} 条历史 K 线")
        print(f"   最新 K 线时间: {datetime.fromtimestamp(ohlcv[-1][0]/1000)}")
    
    async def start(self):
        """启动 WebSocket 监听"""
        await self.initialize()
        
        self.is_running = True
        print(f"🚀 启动实盘模拟交易 (v5)")
        print(f"   交易对: {self.symbol}")
        print(f"   周期: {self.interval}")
        print(f"   初始资金: {self.initial_balance} USDT")
        print(f"   固定亏损额: {self.strategy_config.fixed_loss} USDT")
        print(f"   总仓位上限: {self.strategy_config.max_total_position} USDT")
        print(f"   每日最大亏损: {self.strategy_config.max_daily_loss} USDT")
        
        # 启动 WebSocket
        await self._run_websocket()
    
    async def _run_websocket(self):
        """运行 WebSocket"""
        while self.is_running:
            try:
                # 监听 K 线
                ohlcv = await self.exchange.watch_ohlcv(
                    self.symbol, 
                    self.interval
                )
                
                # 检查是否是收线（新 K 线）
                if len(ohlcv) > 0:
                    latest = ohlcv[-1]
                    current_time = latest[0]
                    
                    if current_time > self.last_kline_time:
                        # 新 K 线收线
                        self.last_kline_time = current_time
                        self.ohlcv_data = ohlcv  # 更新数据
                        
                        # 触发策略检查
                        await self._on_new_kline(ohlcv)
                
            except Exception as e:
                print(f"❌ WebSocket 错误: {e}")
                await asyncio.sleep(5)
    
    async def _on_new_kline(self, ohlcv: List[List]):
        """新 K 线收线时触发"""
        print(f"\n📈 新 K 线: {datetime.fromtimestamp(ohlcv[-1][0]/1000)}")
        
        # v5: 检查并重置每日亏损
        self._check_daily_reset(ohlcv[-1][0])
        
        # 检查持仓状态
        await self._check_positions(ohlcv[-1])
        
        # v5: 检查每日最大亏损
        max_daily_loss = self.strategy_config.max_daily_loss
        if self.position_manager.daily_pnl <= -max_daily_loss:
            print(f"   ⚠️ 当日亏损已达上限 {max_daily_loss} USDT，跳过入场")
            return
        
        # 生成信号
        signal = self._generate_signal(ohlcv)
        
        if signal:
            print(f"   🔔 信号: {signal.side} {signal.pattern_name}")
            # 开仓
            await self._open_position(signal, ohlcv[-1])
        else:
            print(f"   ⏳ 无信号")
    
    def _check_daily_reset(self, current_time: int):
        """v5: 检查并重置每日亏损"""
        current_day = datetime.fromtimestamp(current_time / 1000).strftime('%Y-%m-%d')
        if current_day != self.current_day:
            self.position_manager.reset_daily_pnl()
            self.current_day = current_day
            print(f"   📅 新的一天，重置每日亏损统计")
    
    def _generate_signal(self, ohlcv: List[List]) -> Optional[PatternSignal]:
        """生成交易信号"""
        if len(ohlcv) < 50:
            return None
        
        # 转换为 dict 列表（策略需要）
        records = []
        for k in ohlcv:
            records.append({
                'timestamp': k[0],
                'open': k[1],
                'high': k[2],
                'low': k[3],
                'close': k[4],
                'volume': k[5],
            })
        
        current_idx = len(records) - 1
        positions_count = len(self.positions)
        
        # 调用策略信号
        signal = self.signal_generator.generate_signal(
            records, 
            current_idx, 
            positions_count
        )
        
        return signal
    
    async def _open_position(self, signal: PatternSignal, kline):
        """开仓"""
        current_price = kline[4]  # close
        
        # v5: 使用以损定仓计算仓位
        position_size = self.position_manager.calculate_position_size(
            signal.entry_price, signal.stop_loss
        )
        
        # 检查总仓位上限
        current_total = self.position_manager.get_total_position_size()
        max_total = self.strategy_config.max_total_position
        remaining = max_total - current_total
        position_size = min(position_size, remaining)
        
        if position_size <= 0:
            print(f"   ⚠️ 仓位计算失败或已达总仓位上限")
            return
        
        # 计算数量
        size = position_size / current_price
        
        print(f"   📝 下单: 买入 {size:.6f} @ {current_price}")
        print(f"   💰 仓位金额: {position_size:.2f} USDT")
        
        try:
            # Demo Mode 下单
            order = await self.exchange.create_order(
                symbol=self.symbol,
                type='market',
                side='buy',
                amount=size,
            )
            
            print(f"   ✅ 成交: {order}")
            
            # 创建持仓
            position = Position(
                type='long',
                entry_price=current_price,
                entry_time=kline[0],
                entry_idx=len(self.ohlcv_data) - 1,
                position_size=position_size,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                entry_signal=signal.side,
                entry_pattern=signal.pattern_name,
                thrust=signal.thrust,
                                metadata=signal.metadata or {},
            )
            self.positions.append(position)
            self.position_manager.positions.append(position)
            
            # 更新余额
            self.balance -= position_size
            
        except Exception as e:
            print(f"   ❌ 下单失败: {e}")
    
    async def _check_positions(self, kline):
        """检查持仓，处理止盈止损"""
        if not self.positions:
            return
        
        current_price = kline[4]
        current_high = kline[2]
        current_low = kline[3]
        current_time = kline[0]
        
        to_close = []
        
        for pos in self.positions:
            pos.update_bars()
            pos.update_high_low(current_price)
            
            # 使用风险管理器检查出场
            exit_signal = self.risk_manager.check_exit(
                pos, current_price, current_high, current_low
            )
            
            if exit_signal.should_exit:
                await self._close_position(pos, current_price, exit_signal.reason)
                to_close.append(pos)
        
        # 移除已平仓
        for pos in to_close:
            self.positions.remove(pos)
            if pos in self.position_manager.positions:
                self.position_manager.positions.remove(pos)
    
    async def _close_position(self, position: Position, current_price: float, reason: str):
        """平仓"""
        print(f"   📤 平仓: {reason} @ {current_price}")
        
        try:
            # Demo Mode 平仓
            size = position.position_size / position.entry_price
            
            order = await self.exchange.create_order(
                symbol=self.symbol,
                type='market',
                side='sell',
                amount=size,
            )
            
            print(f"   ✅ 平仓成交: {order}")
            
            # 计算盈亏
            pnl = (current_price - position.entry_price) * size
            pnl_pct = (current_price - position.entry_price) / position.entry_price * 100
            
            # 更新余额
            self.balance += position.position_size + pnl
            
            # v5: 更新每日亏损
            self.position_manager.daily_pnl += pnl
            
            # 记录交易
            trade = Trade(
                entry_time_str=datetime.fromtimestamp(position.entry_time/1000).strftime('%Y-%m-%d %H:%M:%S'),
                entry_price=position.entry_price,
                position=position.type,
                exit_time_str=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                exit_price=current_price,
                hold_bars=position.bars,
                position_size=position.position_size,
                entry_signal=position.entry_signal,
                entry_pattern=position.entry_pattern,
                thrust=position.thrust,
                exit_reason=reason,
                profit_usd=pnl,
                pnl_pct=pnl_pct,
            )
            
            self.trades.append(trade)
            self.position_manager.trades.append(trade)
            
            print(f"   💰 盈亏: {pnl:.2f} USDT ({pnl_pct:.2f}%)")
            print(f"   💵 当前余额: {self.balance:.2f} USDT")
            print(f"   📊 今日盈亏: {self.position_manager.daily_pnl:.2f} USDT")
            
        except Exception as e:
            print(f"   ❌ 平仓失败: {e}")
    
    async def stop(self):
        """停止"""
        self.is_running = False
        print("\n🛑 停止实盘模拟")
    
    def get_status(self) -> Dict:
        """获取状态（供UI显示）"""
        return {
            'balance': self.balance,
            'positions': self.positions,
            'trades': self.trades,
            'daily_pnl': self.position_manager.daily_pnl,
            'current_signal': None,  # 实时计算
        }


async def main():
    """主函数"""
    # 配置 - 只覆盖需要修改的参数，其他使用默认值
    config = {
        'demo_api_key': os.getenv('DEMO_BINANCE_KEY', 'YOUR_API_KEY'),
        'demo_api_secret': os.getenv('DEMO_BINANCE_SECRET', 'YOUR_API_SECRET'),
        'symbol': 'BTC/USDT',
        'interval': '5m',
        'initial_balance': 10000,

        # 策略参数（覆盖默认值）
        'enable_rsi_filter': True,
    }
    
    # 创建并启动
    simulator = LiveSimulator(config)
    
    try:
        await simulator.start()
    except KeyboardInterrupt:
        await simulator.stop()


if __name__ == '__main__':
    asyncio.run(main())
