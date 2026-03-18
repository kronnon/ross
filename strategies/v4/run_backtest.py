#!/usr/bin/env python3
"""
快速回测脚本 - 调用v4模块
"""
import sys
import os
from datetime import datetime

# 添加v4到路径
v4_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, v4_dir)

from pymongo import MongoClient
from config import StrategyConfig
from backtest import BacktestEngine, export_to_excel

# MongoDB连接
client = MongoClient('mongodb://localhost:27017/')
db = client['trading-data']

def get_klines(symbol: str, interval: str, start: str, end: str):
    """从MongoDB获取K线数据"""
    collection = db[f'{symbol}_{interval}']
    
    # 使用UTC时间
    start_dt = datetime.fromisoformat(f'{start}T00:00:00+00:00')
    end_dt = datetime.fromisoformat(f'{end}T00:00:00+00:00')
    start_ts = int(start_dt.timestamp() * 1000)
    end_ts = int(end_dt.timestamp() * 1000)
    
    records = list(collection.find({
        'time': {'$gte': start_ts, '$lt': end_ts}
    }).sort('time', 1))
    
    # 提取需要的字段
    return [{
        'time': r['time'],
        'open': r['open'],
        'high': r['high'],
        'low': r['low'],
        'close': r['close'],
        'volume': r.get('qty', 0),
    } for r in records]

def main():
    if len(sys.argv) < 5:
        print("Usage: python run_backtest.py <symbol> <interval> <start> <end>")
        print("Example: python run_backtest.py btc 5m 2026-01-01 2026-03-01")
        sys.exit(1)
    
    symbol = sys.argv[1]
    interval = sys.argv[2]
    start = sys.argv[3]
    end = sys.argv[4]
    
    print(f"获取 {symbol.upper()} {interval} 数据 ({start} ~ {end})...")
    records = get_klines(symbol, interval, start, end)
    print(f"获取到 {len(records)} 条K线数据")
    
    if len(records) == 0:
        print("没有数据！")
        sys.exit(1)
    
    # 使用MEMORY中的参数创建配置
    config_dict = {
        'leverage': 10,
        'initial_balance': 100.0,
        'min_trade_interval': 3,
        'max_hold_bars': 288,
        'stop_loss_pct': 5.0,
        'take_profit_pct': 2.0,
        'risk_pct': 1.0,
        'max_position': 500.0,
        'use_position_size_mode': False,
        'lookback_bars': 10,
        'min_thrust': 0.3,
        'p2_p3_lookback': 5,
        'max_concurrent_positions': 3,
        'slippage_pct': 0.1,
        'fill_rate': 0.9,
        'commission_rate': 0.04,
        'min_volume': 1000,
        'price_delay': True,
    }
    
    config = StrategyConfig.from_dict(config_dict)
    
    # 运行回测
    print("\n运行回测 (杠杆10x, 止损5%, 多空双做)...")
    engine = BacktestEngine(config)
    trades, missed = engine.run(records)
    stats = engine.get_stats()
    
    print("\n" + "="*50)
    print(f"回测结果 - {symbol.upper()} {interval} ({start} ~ {end})")
    print("="*50)
    print(f"数据量:     {len(records)} 条")
    print(f"交易次数:   {stats['total_trades']}")
    print(f"胜率:       {stats['win_rate']:.1f}%")
    print(f"总盈亏:     {stats['total_pnl']:.2f} USDT")
    print(f"最终余额:   {stats['final_balance']:.2f} USDT")
    print(f"盈利交易:   {stats['wins']}")
    print(f"亏损交易:   {stats['losses']}")
    print("="*50)
    
    # 导出Excel
    output_dir = '/Users/makaihong/.openclaw/workspaces/ross/outputs'
    os.makedirs(output_dir, exist_ok=True)
    excel_path = f"{output_dir}/ross_trading_v4_{symbol}_{interval}_{start.replace('-','')}_{end.replace('-','')}_trades.xlsx"
    export_to_excel(trades, missed, excel_path, config)
    print(f"\n交易记录已导出: {excel_path}")
    
    return {'trades': trades, 'stats': stats, 'missed': missed}

if __name__ == '__main__':
    main()
