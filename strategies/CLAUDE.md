# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Ross 交易策略系统 - 基于 Joe Ross 的洛氏霍克 (Ross Hook) 交易方法实现的量化回测框架。当前最新版本为 v5。

## 常用命令

```bash
# 运行回测 (v5)
cd ~/.openclaw/workspaces/ross/strategies/v5
python3 run_backtest.py <symbol> <interval> <year>
# 示例: python3 run_backtest.py eth 5m 2025

# 快速测试 (单月)
python3 test_backtest.py

# 直接运行模块
python3 __init__.py --symbol btc --interval 5m --year 2025
```

## 架构

```
v5/
├── config.py      # 配置管理 (StrategyConfig dataclass)
├── signals.py     # 信号生成 (形态识别: 1-2-3, Ledge, Trading Range, Ross Hook)
├── position.py    # 仓位管理 (持仓/交易记录)
├── risk.py        # 风险管理 (止损/止盈/移动止损/ATR止损)
├── backtest.py    # 回测引擎 + Excel导出
├── live_sim.py    # 实盘模拟
└── __init__.py    # 模块入口 + quick_backtest() 快速接口
```

## 核心概念

### 形态识别 (Law of Charts)
- **1-2-3 High/Low**: 趋势反转形态
- **Ross Hook**: 突破后的第一次回撤
- **Ledge**: 旗杆形态
- **Trading Range**: 交易区间突破

### 仓位模式 (v5)
- **以损定仓**: `fixed_loss / stop_loss_pct` = 仓位
- **固定仓位**: `use_position_size_mode=True` + `position_size`

### 数据源
MongoDB `trading-data` 数据库，集合命名 `{symbol}_{interval}` (如 `eth_5m`)。

## 使用示例

```python
from v5 import StrategyConfig, BacktestEngine, export_to_excel

config = StrategyConfig.from_dict({
    'leverage': 10,
    'initial_balance': 100,
    'stop_loss_pct': 5.0,
    'take_profit_pct': 2.0,
    'fixed_loss': 2.0,  # 每次固定亏损 2 USDT
})

engine = BacktestEngine(config)
trades, missed = engine.run(records)
export_to_excel(trades, missed, 'output.xlsx', config)
```

## v4 vs v5 主要差异

| 功能 | v4 | v5 |
|------|----|----|
| 仓位计算 | `risk_pct` | `fixed_loss` |
| 总仓位上限 | 无 | `max_total_position` |
| 固定仓位模式 | 无 | `use_position_size_mode` |
| 双边手续费 | 单边 | 双边 (×2) |
| KDJ/BOLL/EMA 过滤 | 无 | 有 |

## 相关文档

- `ross_trading.md` - Ross 交易法知识库
- `v5/README.md` - v5 详细文档
- `v4/README.md` - v4 详细文档
