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
- **time**: K线开始时间 (Unix时间戳)
- **rsi**: RSI指标值
- **kdj**: KDJ指标对象 {k, d, j}
- **boll**: BOLL指标对象 {upper, middle, lower}

## 使用方法

### 命令行运行
```bash
cd /Users/makaihong/.openclaw/skills/trading_data
source venv/bin/activate
python main.py --symbol <币种> --interval <周期>
```

### 参数说明
| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| --symbol | 是 | - | 币种: btc, eth, bnb |
| --interval | 否 | 5m | K线周期: 5m, 15m, 1h, 4h, 1d |
| --limit | 否 | 50 | 获取K线数量 |

### 示例
```bash
# 获取BTC 5分钟数据
python main.py --symbol btc --interval 5m

# 获取ETH 1小时数据
python main.py --symbol eth --interval 1h

# 获取BNB 15分钟数据，100条
python main.py --symbol bnb --interval 15m --limit 100
```

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
