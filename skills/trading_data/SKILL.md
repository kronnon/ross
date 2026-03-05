---
name: trading_data
description: "从Binance API获取加密货币K线数据，存储到MongoDB，包含技术指标 (RSI/KDJ/BOLL)。当用户询问加密货币行情、K线数据、技术指标、RSI/KDJ/BOLL分析时使用。"
---

# trading_data

## Description
从Binance API获取加密货币K线数据，存储到MongoDB，包含技术指标 (RSI/KDJ/BOLL)。

## 数据结构
每条记录包含以下字段：
- **price**: 收盘价
- **qty**: 成交量
- **time**: K线开始时间 (Unix时间戳，毫秒)
- **rsi**: RSI指标值 (14周期)
- **kdj**: KDJ指标对象 {k, d, j} (9周期)
- **boll**: BOLL指标对象 {upper, middle, lower} (20周期)
- **ema**: EMA指标对象 {ema9, ema21} (9和21周期)

**注意：** 每根K线独立计算技术指标，前21根K线指标可能为None（因数据不足）

## 使用方法

### 命令行运行
```bash
cd ~/.openclaw/workspaces/ross/skills/trading_data
./venv/bin/python3 main.py --symbol <币种> --interval <周期> [--limit N] [--start YYYY-MM-DD] [--end YYYY-MM-DD]
```

### 获取历史数据
```bash
# 获取指定时间范围
./venv/bin/python3 main.py --symbol btc --interval 5m --limit 1000 --start 2025-01-01 --end 2025-12-31

# 获取2025年全年数据（分批获取脚本）
./venv/bin/python3 fetch_2025.py --force
```

### 快速获取最近数据
```bash
# 获取BTC 5分钟数据，最近1000条
python main.py --symbol btc --interval 5m

## Python调用
```python
import sys
sys.path.append('/Users/makaihong/.openclaw/skills/trading_data')
from main import get_recent_records

# 获取最近10条数据
records = get_recent_records("btc", "5m", 10)
for r in records:
    print(r)
```

## Collection命名规则
`{symbol}_{interval}` 例如: `btc_5m`, `eth_1h`, `bnb_15m`

## 支持的币种
- btc (BTCUSDT)
- eth (ETHUSDT)
- bnb (BNBUSDT)
