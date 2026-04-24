# Ross 交易策略 v5.0

> 洛氏霍克交易系统 - 模块化架构

## 版本更新

### v5.0 最新修复 (2026-04-23)

| 修复项 | 说明 |
|--------|------|
| **双边手续费** | `commission × 2`，符合币安合约真实收费 |
| **交易排序** | 导出 Excel 时按入场时间排序，余额计算连续 |
| **统计准确** | 修复 `get_stats()` 只统计最后一个月的问题 |
| **统计摘要 Sheet** | 新增「统计摘要」Sheet，包含正确的累计数据 |

### v5.0 核心功能

| 功能 | 说明 |
|------|------|
| **以损定仓** | 使用 `fixed_loss` 替代 `risk_pct`，每次固定亏损金额 |
| **总仓位上限** | `max_total_position` 控制所有持仓合计上限 |
| **固定仓位模式** | `use_position_size_mode=True` 时使用固定仓位金额 |
| **形态识别精细化** | `max_lookback`, `pattern_lookback`, `hook_search_range` 等参数 |
| **KDJ/BOLL/EMA 过滤器** | 多指标共振过滤信号 |
| **每日最大亏损** | `max_daily_loss` 控制每日亏损上限 |
| **跳过 Ross Hook** | `skip_ross_hook=True` 直接用 P3 入场 |
| **突破前瞻确认** | `breakout_lookahead` 控制 Hook 后几根 K 线内确认突破 |

---

## 快速开始

```python
from v5 import StrategyConfig, BacktestEngine, export_to_excel

# 配置
config = StrategyConfig.from_dict({
    'leverage': 10,
    'initial_balance': 100,
    'stop_loss_pct': 5.0,
    'take_profit_pct': 2.0,
    'fixed_loss': 2.0,
    'max_total_position': 1000,
    'use_position_size_mode': False,  # True=固定仓位, False=以损定仓
})

# 运行回测
engine = BacktestEngine(config)
trades, missed = engine.run(records)

# 导出 Excel（包含统计摘要）
export_to_excel(trades, missed, 'output.xlsx', config)
```

---

## 运行回测

### 方式1：命令行脚本

```bash
cd ~/.openclaw/workspaces/ross/strategies/v5

# 回测 ETH 5分钟 2025年数据
python3 run_backtest.py eth 5m 2025

# 回测 2026年
python3 run_backtest.py eth 5m 2026
```

输出文件保存到 `~/.openclaw/workspaces/ross/outputs/`

### 方式2：临时参数（不改配置）

```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from config import StrategyConfig
from backtest import BacktestEngine, export_to_excel
import pymongo, os
from datetime import datetime, timezone

symbol, interval, year = 'eth', '5m', 2025
client = pymongo.MongoClient(os.getenv('MONGO_URL','mongodb://localhost:27017/'))
recs = [{k: r[k] for k in ['time','open','high','low','close','volume']}
        for r in client['trading-data'][f'{symbol}_{interval}'].find({}).sort('time',1)
        if datetime.fromtimestamp(r['time']/1000, tz=timezone.utc).year == year]

# 临时参数
config = StrategyConfig.from_dict({'use_position_size_mode': True, 'position_size': 100.0})
engine = BacktestEngine(config)
trades, missed = engine.run(recs)
export_to_excel(trades, missed, f'outputs/test_{symbol}_{interval}_{year}.xlsx', config)
print(f'完成: {len(trades)}笔')
"
```

### 方式3：修改 config.py 默认值

编辑 `config.py` 修改默认参数：

```python
use_position_size_mode: bool = True   # True=固定仓位, False=以损定仓
position_size: float = 100.0        # 固定仓位金额 USDT
commission_rate: float = 0.04       # 单边手续费率%（实际双边×2）
```

---

## 配置参数

### 仓位管理

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `use_position_size_mode` | bool | False | True=固定仓位, False=以损定仓 |
| `position_size` | float | 100.0 | 固定仓位金额 USDT（固定仓位模式时生效） |
| `fixed_loss` | float | 2.0 | 固定亏损额 USDT（以损定仓模式时生效） |
| `max_position` | float | 500.0 | 单次最大仓位上限 |
| `max_total_position` | float | 1000.0 | 总仓位上限 |

### 止损止盈

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `stop_loss_pct` | float | 5.0 | 止损比例 % |
| `take_profit_pct` | float | 2.0 | 止盈比例 % |

### 手续费（重要）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `commission_rate` | float | 0.04 | 单边手续费率 % |
| `slippage_pct` | float | 0.1 | 滑点百分比 |
| `fill_rate` | float | 0.9 | 成交率 |

**实际手续费 = position_size × commission_rate × 2**（双边收费）

### 形态识别

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `lookback_bars` | int | 10 | 回看 K 线数 |
| `min_thrust` | float | 0.3 | 最小突破幅度 % |
| `skip_ross_hook` | bool | False | 跳过 Ross Hook |
| `breakout_lookahead` | int | 3 | Hook 后几根内确认突破 |
| `hook_search_range` | int | 8 | Ross Hook 搜索范围 |

### 过滤器

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enable_rsi_filter` | bool | False | RSI 过滤 |
| `enable_kdj_filter` | bool | False | KDJ 过滤 |
| `enable_boll_filter` | bool | False | BOLL 过滤 |
| `enable_ema_filter` | bool | False | EMA 过滤 |

---

## 以损定仓计算

```
仓位 = fixed_loss / 止损%
```

**示例**：
- `fixed_loss = 2.0` USDT
- `stop_loss_pct = 5.0%`
- 仓位 = 2.0 / 0.05 = 40 USDT（10倍杠杆 → 400 USDT 名义仓位）

---

## 输出文件

Excel 包含以下 Sheet：

1. **交易记录** - 按入场时间排序，每笔包含手续费、盈亏、余额
2. **统计摘要** - 总交易数、胜率、总盈亏、最终余额、收益率
3. **错过的信号** - 未入场的信号及原因
4. **配置参数** - 本次回测使用的参数

---

## 与 v4 的差异

| 功能 | v4 | v5 |
|------|----|----|
| 以损定仓 | `risk_pct` | `fixed_loss` |
| 总仓位上限 | ❌ | ✅ |
| 固定仓位模式 | ❌ | ✅ |
| 多周期确认 | ✅ | ✅ |
| KDJ/BOLL/EMA 过滤 | ✅ | ✅ |
| 每日最大亏损 | ✅ | ✅ |
| 形态破坏止损 | ✅ | ✅ |
| 跳过 Ross Hook | ✅ | ✅ |
| 双边手续费 | ❌ | ✅ |
| 交易排序导出 | ❌ | ✅ |

---

## 文件结构

```
v5/
├── __init__.py      # 模块导出
├── config.py        # 配置管理
├── signals.py       # 信号生成
├── position.py      # 仓位管理
├── risk.py          # 风险管理
├── backtest.py      # 回测引擎
├── live_sim.py      # 实盘模拟
└── README.md        # 本文档
```

---

## 作者

Ross 交易策略 - 洛氏霍克交易研究
