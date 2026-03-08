# Ross交易系统 v4.0 文档

## 版本信息

| 项目 | 内容 |
|------|------|
| **版本号** | v4.0.0 |
| **创建时间** | 2026-03-08 |
| **最后更新** | 2026-03-08 |
| **状态** | 开发完成 |

---

## 代码结构

```
strategies/v4/
├── __init__.py          # 主入口，导出所有接口
├── config.py            # 配置管理（StrategyConfig类）
├── signals.py           # 信号生成（形态识别）
│   ├── 1-2-3形态 + Ross Hook
│   ├── Ledge旗杆形态
│   ├── Trading Range交易区间
│   ├── RSI过滤
│   └── 多周期确认
├── risk.py              # 风险管理（止损/止盈/移动止损/ATR止损/趋势过滤）
├── position.py          # 仓位管理（持仓/交易记录）
└── backtest.py          # 回测引擎
```

---

## 配置参数

### 基础配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `leverage` | int | 10 | 杠杆倍数 |
| `initial_balance` | float | 100.0 | 初始余额 |
| `min_trade_interval` | int | 3 | 最小交易间隔（K线数） |
| `max_hold_bars` | int | 288 | 最大持仓K线数 |

### 止损止盈

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `stop_loss_pct` | float | 5.0 | 止损比例 % |
| `take_profit_pct` | float | 2.0 | 止盈比例 % |

### 以损定仓

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `risk_pct` | float | 1.0 | 风险比例 % |
| `max_position` | float | 500.0 | 最大仓位上限 |
| `use_position_size_mode` | bool | False | True=固定仓位, False=以损定仓 |

### 形态识别

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `lookback_bars` | int | 10 | 回看K线数 |
| `min_thrust` | float | 0.3 | 最小突破幅度 % |

### 多仓位

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_concurrent_positions` | int | 3 | 最大同时持仓数 |

### 真实交易模拟

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `slippage_pct` | float | 0.1 | 滑点百分比 |
| `fill_rate` | float | 0.9 | 成交率 |
| `commission_rate` | float | 0.04 | 手续费率 % |
| `min_volume` | float | 1000 | 最小成交量过滤 |

### 风险管理（可选）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enable_trailing_stop` | bool | False | 开启移动止损 |
| `trailing_stop_pct` | float | 0 | 移动止损触发盈利% |
| `enable_partial_tp` | bool | False | 开启分批止盈 |
| `partial_tp_pct` | float | 0 | 分批止盈触发盈利% |
| `enable_atr_stop` | bool | False | 开启ATR止损 |
| `atr_period` | int | 14 | ATR周期 |
| `atr_multiplier` | float | 2.0 | ATR倍数 |
| `enable_trend_filter` | bool | False | 开启趋势过滤 |

### 过滤器（可选）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enable_rsi_filter` | bool | False | 开启RSI过滤 |
| `rsi_period` | int | 14 | RSI周期 |
| `rsi_overbought` | float | 70 | RSI超买阈值 |
| `rsi_oversold` | float | 30 | RSI超卖阈值 |

### 多周期确认（可选）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `higher_timeframe` | str | '' | 大级别周期，空=不开启，如'15m'、'1h' |
| `ht_lookback` | int | 50 | 大周期回看K线数 |

---

## 使用方式

### 方式1：快速回测

```python
from v4 import quick_backtest

result = quick_backtest(records, stop_loss=5.0, take_profit=2.0)
```

### 方式2：详细使用

```python
from v4 import BacktestEngine, StrategyConfig
import pymongo

# 加载配置
config_dict = {
    'leverage': 10,
    'initial_balance': 100,
    'stop_loss_pct': 5.0,
    'take_profit_pct': 2.0,
    # ... 其他配置
}
config = StrategyConfig.from_dict(config_dict)

# 加载数据
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client['trading-data']
records = list(db['eth_5m'].find().limit(50000))

# 运行回测
engine = BacktestEngine(config)
trades, missed = engine.run(records)

# 获取统计
stats = engine.get_stats()
```

### 方式3：多周期确认

```python
# 加载两个周期数据
records_5m = get_5m_data()
records_15m = get_15m_data()

config_dict['higher_timeframe'] = '15m'  # 开启多周期确认
config = StrategyConfig.from_dict(config_dict)

engine = BacktestEngine(config)
trades, missed = engine.run(records_5m, records_15m)
```

### 方式4：MongoDB配置管理

```python
from v4 import ConfigManager, BacktestEngine

# 初始化
mgr = ConfigManager(db)
config = mgr.load("v4.0.0")

# 运行
engine = BacktestEngine(config)
trades, missed = engine.run(records)

# 热更新
new_config = mgr.reload("v4.1.0")
engine.reload_config(new_config)
```

---

## 更新日志

### v4.0.0 (2026-03-08) - 初始版本

**新增功能：**
- 模块化架构（config/signals/risk/position/backtest）
- 1-2-3形态 + Ross Hook识别（优化版）
- Ledge旗杆形态识别
- Trading Range交易区间识别
- RSI过滤（enable_rsi_filter）
- 多周期确认（higher_timeframe）
- 移动止损（enable_trailing_stop）
- 分批止盈（enable_partial_tp）
- ATR止损（enable_atr_stop）
- 趋势过滤（enable_trend_filter）
- MongoDB配置热更新（ConfigManager）
- 向量化配置管理（无默认值，由量化系统传入）

---

## 注意事项

1. **配置由量化系统维护** - 所有配置参数由外部传入，策略只负责读取
2. **配置无默认值** - 必需参数必须传入，否则报错
3. **MongoDB配置** - 支持从数据库加载版本配置
4. **多周期数据** - 需要手动传入大周期数据
