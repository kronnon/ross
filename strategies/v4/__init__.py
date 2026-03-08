"""
Ross交易系统 v4.0 - 模块化架构

配置由量化系统维护，策略只负责读取使用
"""

from config import StrategyConfig, ConfigManager
from signals import SignalGenerator, PatternSignal, create_signal_generator
from risk import RiskManager, ExitSignal, create_risk_manager
from position import PositionManager, Position, Trade, create_position_manager
from backtest import BacktestEngine, run_backtest, export_to_excel

__version__ = "4.0.0"

__all__ = [
    # 配置
    'StrategyConfig',
    'ConfigManager',
    
    # 信号
    'SignalGenerator',
    'PatternSignal',
    'create_signal_generator',
    
    # 风险
    'RiskManager',
    'ExitSignal',
    'create_risk_manager',
    
    # 仓位
    'PositionManager',
    'Position',
    'Trade',
    'create_position_manager',
    
    # 回测
    'BacktestEngine',
    'run_backtest',
    'export_to_excel',
]


def create_engine(config: StrategyConfig) -> BacktestEngine:
    """创建回测引擎"""
    return BacktestEngine(config)


# ==================== 快速使用示例 ====================

def quick_backtest(records: list, 
                   leverage: int = 10,
                   stop_loss: float = 5.0,
                   take_profit: float = 2.0,
                   **kwargs):
    """
    快速回测（简化接口）
    
    Args:
        records: K线数据列表
        leverage: 杠杆倍数
        stop_loss: 止损比例 %
        take_profit: 止盈比例 %
        **kwargs: 其他配置参数
    
    Returns:
        dict: 包含 trades, stats, missed_signals
    """
    config_dict = {
        'leverage': leverage,
        'initial_balance': 100,
        'min_trade_interval': 3,
        'max_hold_bars': 288,
        'stop_loss_pct': stop_loss,
        'take_profit_pct': take_profit,
        'risk_pct': 1.0,
        'max_position': 500,
        'use_position_size_mode': False,
        'lookback_bars': 10,
        'min_thrust': 0.3,
        'max_concurrent_positions': 3,
        'slippage_pct': 0.1,
        'fill_rate': 0.9,
        'commission_rate': 0.04,
        'min_volume': 1000,
        'price_delay': True,
        **kwargs
    }
    
    config = StrategyConfig.from_dict(config_dict)
    
    engine = BacktestEngine(config)
    trades, missed = engine.run(records)
    stats = engine.get_stats()
    
    return {
        'trades': trades,
        'stats': stats,
        'missed_signals': missed,
        'config': config,
    }


if __name__ == "__main__":
    import argparse
    import pymongo
    import os
    from datetime import datetime
    
    parser = argparse.ArgumentParser(description='Ross交易系统 v4.0')
    parser.add_argument('--symbol', type=str, default='eth', help='交易对')
    parser.add_argument('--interval', type=str, default='5m', help='周期')
    parser.add_argument('--limit', type=int, default=50000, help='数据量')
    parser.add_argument('--year', type=int, default=None, help='年份')
    args = parser.parse_args()
    
    print("=" * 60)
    print(f"Ross交易系统 v4.0 - {args.symbol.upper()} {args.interval}")
    print("=" * 60)
    
    # 加载数据
    client = pymongo.MongoClient(os.getenv('MONGO_URL', os.getenv('MONGO_URI', 'mongodb://localhost:27017/')))
    db = client['trading-data']
    
    symbol_map = {'xau': 'xauusdt', 'xag': 'xagusdt'}
    db_symbol = symbol_map.get(args.symbol, args.symbol)
    collection = db[f'{db_symbol}_{args.interval}']
    
    query = {}
    if args.year:
        start = int(datetime(args.year, 1, 1).timestamp() * 1000)
        end = int(datetime(args.year + 1, 1, 1).timestamp() * 1000)
        query = {'time': {'$gte': start, '$lt': end}}
        print(f"时间范围: {args.year}年")
    
    records = list(collection.find(query).sort('time', 1).limit(args.limit))
    print(f"\n加载数据: {len(records)} 条")
    
    # 运行回测（使用优化后的配置）
    default_config = {
        'leverage': 10,
        'initial_balance': 100,
        'min_trade_interval': 3,
        'max_hold_bars': 288,
        'stop_loss_pct': 1.0,   # 1%
        'take_profit_pct': 5.0, # 5%
        'risk_pct': 1.0,
        'max_position': 500,
        'use_position_size_mode': False,
        'lookback_bars': 10,
        'min_thrust': 0.3,
        'max_concurrent_positions': 3,
        'slippage_pct': 0.1,
        'fill_rate': 0.9,
        'commission_rate': 0.04,
        'min_volume': 1000,
        'price_delay': True,
    }
    config = StrategyConfig.from_dict(default_config)
    engine = BacktestEngine(config)
    trades, missed = engine.run(records)
    
    # 统计
    stats = engine.get_stats()
    print(f"\n=== 回测统计 ===")
    print(f"总交易: {stats['total_trades']}")
    print(f"盈利: {stats['wins']} ({stats['win_rate']:.1f}%)")
    print(f"亏损: {stats['losses']}")
    print(f"总盈亏: {stats['total_pnl']:.2f} USDT")
    print(f"最终余额: {stats['final_balance']:.2f} USDT")
    
    # 出场原因
    reasons = engine.get_exit_reasons()
    print(f"\n=== 出场原因 ===")
    for r, c in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  {r}: {c}")
    
    # 导出
    output_dir = os.path.expanduser("~/.openclaw/workspaces/ross/outputs")
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{output_dir}/ross_v4_{args.symbol}_{args.interval}_trades.xlsx"
    export_to_excel(trades, missed, filename, config)
    print(f"\nExcel已保存: {filename}")
