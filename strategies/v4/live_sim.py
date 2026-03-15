#!/usr/bin/env python3
"""
实盘模拟交易 - Binance Demo Mode

功能：
- WebSocket 实时获取 K 线
- 复用 v4 策略信号
- Demo Mode 模拟下单
- 持仓管理
- 交易记录输出
"""

import asyncio
import ccxt
import pandas as pd
from datetime import datetime
from typing import List, Optional, Dict
import json
import os
import sys

# 添加 strategies 到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from signals import SignalGenerator
from config import StrategyConfig
from position import Position, Trade, PositionManager


class LiveSimulator:
    """实盘模拟交易"""
    
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
        
        # 状态
        self.last_kline_time = 0
        self.is_running = False
        
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
        print(f"🚀 启动实盘模拟交易")
        print(f"   交易对: {self.symbol}")
        print(f"   周期: {self.interval}")
        print(f"   初始资金: {self.initial_balance} USDT")
        
        # 启动 WebSocket
        await self._run_websocket()
    
    async def _run_websocket(self):
        """运行 WebSocket"""
        # CCXT 的 WebSocket 方法
        # 注意：CCXT 的 WebSocket 支持需要调用 watch_ohlcv
        
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
        
        # 检查持仓状态
        await self._check_positions(ohlcv[-1])
        
        # 生成信号
        signal = self._generate_signal(ohlcv)
        
        if signal:
            print(f"   🔔 信号: {signal.signal_type} {signal.pattern_name}")
            # 开仓
            await self._open_position(signal, ohlcv[-1])
        else:
            print(f"   ⏳ 无信号")
    
    def _generate_signal(self, ohlcv: List[List]) -> Optional[object]:
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
    
    async def _open_position(self, signal, kline):
        """开仓"""
        current_price = kline[4]  # close
        position_size = self.strategy_config.max_position  # 简化：用固定仓位
        
        # 计算仓位
        size = position_size / current_price
        
        print(f"   📝 下单: 买入 {size:.6f} BTC @ {current_price}")
        
        try:
            # Demo Mode 下单
            order = await self.exchange.create_order(
                symbol=self.symbol,
                type='market',
                side='buy',
                amount=size,
                # price=current_price,  # 市价单不需要价格
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
                entry_signal=signal.signal_type,
                entry_pattern=signal.pattern_name,
                thrust=signal.thrust,
            )
            self.positions.append(position)
            
            # 更新余额
            self.balance -= position_size
            
        except Exception as e:
            print(f"   ❌ 下单失败: {e}")
    
    async def _check_positions(self, kline):
        """检查持仓，处理止盈止损"""
        if not self.positions:
            return
        
        current_price = kline[4]
        current_time = kline[0]
        
        to_close = []
        
        for pos in self.positions:
            pos.update_bars()
            pos.update_high_low(current_price)
            
            should_close = False
            reason = ""
            
            # 止损
            if pos.type == 'long' and current_price <= pos.stop_loss:
                should_close = True
                reason = "止损"
            # 止盈
            elif pos.type == 'long' and current_price >= pos.take_profit:
                should_close = True
                reason = "止盈"
            # 日内平仓（下午3点前）
            elif datetime.now().hour >= 15:
                should_close = True
                reason = "日内平仓"
            
            if should_close:
                await self._close_position(pos, current_price, reason)
                to_close.append(pos)
        
        # 移除已平仓
        for pos in to_close:
            self.positions.remove(pos)
    
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
            
            print(f"   💰 盈亏: {pnl:.2f} USDT ({pnl_pct:.2f}%)")
            print(f"   💵 当前余额: {self.balance:.2f} USDT")
            
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
            'current_signal': None,  # 实时计算
        }


async def main():
    """主函数"""
    # 配置（最新版本参数）
    config = {
        'demo_api_key': os.getenv('DEMO_BINANCE_KEY', 'KMshMCv9TTCrayN3F2QlWDAJL0BzNFAYZR6saAwvEFZvpxSWSmvMToE5st2bj6cA'),
        'demo_api_secret': os.getenv('DEMO_BINANCE_SECRET', 'DbwIw1OFQdDVBD7rhbBN94nueJS71AL1kvH8RT0ltX7i64wr1YSr3xSPTHcLqwSK'),
        'symbol': 'BTC/USDT',
        'interval': '5m',
        'initial_balance': 10000,
        
        # 策略参数（v4 最新版）
        'leverage': 10,
        'initial_balance': 100.0,
        'min_trade_interval': 3,
        'max_hold_bars': 288,
        'stop_loss_pct': 5.0,
        'take_profit_pct': 2.0,
        'risk_pct': 1.0,
        'max_position': 500.0,
        'lookback_bars': 10,
        'min_thrust': 0.3,
        'max_concurrent_positions': 3,
        
        # 补充参数
        'use_position_size_mode': False,
        'slippage_pct': 0.1,
        'fill_rate': 0.9,
        'commission_rate': 0.04,
        'min_volume': 1000,
    }
    
    # 创建并启动
    simulator = LiveSimulator(config)
    
    try:
        await simulator.start()
    except KeyboardInterrupt:
        await simulator.stop()


if __name__ == '__main__':
    asyncio.run(main())
