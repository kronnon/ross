#!/usr/bin/env python3
"""运行回测脚本"""
import sys
import os
import pymongo
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import StrategyConfig
from backtest import BacktestEngine, export_to_excel

def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else 'eth'
    interval = sys.argv[2] if len(sys.argv) > 2 else '5m'
    year = int(sys.argv[3]) if len(sys.argv) > 3 else 2025
    
    print('=' * 60)
    print(f'Ross交易系统 v5.0 - {symbol.upper()} {interval} {year}年')
    print('=' * 60)
    
    # 加载数据
    client = pymongo.MongoClient(os.getenv('MONGO_URL', os.getenv('MONGO_URI', 'mongodb://localhost:27017/')))
    db = client['trading-data']
    collection = db[f'{symbol}_{interval}']
    
    # 时间范围 - 使用 UTC 时区（与 v4 一致）
    start_dt = datetime.fromisoformat(f'{year}-01-01T00:00:00+00:00')
    end_dt = datetime.fromisoformat(f'{year+1}-01-01T00:00:00+00:00')
    start_ts = int(start_dt.timestamp() * 1000)
    end_ts = int(end_dt.timestamp() * 1000)
    
    # 直接查询 MongoDB (获取所有数据后过滤，避免 Int64 查询问题)
    all_records = list(collection.find({}).sort('time', 1))
    
    # 过滤时间范围
    records = [r for r in all_records if start_ts <= r['time'] < end_ts]
    
    # 提取需要的字段
    records = [{
        'time': r['time'],
        'open': r['open'],
        'high': r['high'],
        'low': r['low'],
        'close': r['close'],
        'volume': r.get('qty', 0),
    } for r in records]
    
    print(f'加载数据: {len(records)} 条')
    
    if not records:
        print('无数据，退出')
        return
    
    # 配置 - 使用默认值，只覆盖需要修改的参数
    config = StrategyConfig.from_dict({})
    
    engine = BacktestEngine(config)
    trades, missed = engine.run(records)
    stats = engine.get_stats()
    
    print(f'\n=== 回测统计 ===')
    print(f'总交易: {stats["total_trades"]}')
    print(f'盈利: {stats["wins"]} ({stats["win_rate"]:.1f}%)')
    print(f'亏损: {stats["losses"]}')
    print(f'总盈亏: {stats["total_pnl"]:.2f} USDT')
    print(f'最终余额: {stats["final_balance"]:.2f} USDT')
    
    reasons = engine.get_exit_reasons()
    print(f'\n=== 出场原因 ===')
    for r, c in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f'  {r}: {c}')
    
    # 导出
    output_dir = os.path.expanduser('~/.openclaw/workspaces/ross/outputs')
    os.makedirs(output_dir, exist_ok=True)
    filename = f'{output_dir}/ross_v5_{symbol}_{interval}_{year}_trades.xlsx'
    export_to_excel(trades, missed, filename, config)
    print(f'\nExcel已保存: {filename}')

if __name__ == '__main__':
    main()
