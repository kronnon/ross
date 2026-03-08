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
./venv/bin/python3 main.py --symbol <币种> --interval <周期> [参数]
```

### 参数说明
| 参数 | 说明 | 示例 |
|------|------|------|
| --symbol | 币种 (任意Binance支持币种) | --symbol sol |
| --interval | K线周期 (5m/15m/1h/4h/1d) | --interval 5m |
| --limit | 获取数量，默认50 | --limit 100 |
| --start | 开始时间 (YYYY-MM-DD) | --start 2025-01-01 |
| --end | 结束时间 (YYYY-MM-DD) | --end 2025-12-31 |
| --max | 历史数据最大获取量 | --max 50000 |

### 获取历史数据
```bash
# 获取2025年全年数据 (推荐使用独立脚本)
cd ~/.openclaw/workspaces/ross/skills/trading_data

# 使用专用脚本获取全年数据 (推荐)
cat > fetch_year.py << 'SCRIPT'
#!/usr/bin/env python3
import sys
sys.path.append('.')
import main
import time

SYMBOL = "sol"  # 币种
INTERVAL = "5m"  # 周期
YEAR = 2025  # 年份

months = []
for m in range(1, 13):
    start = f"{YEAR}-{m:02d}-01"
    if m == 12:
        end = f"{YEAR+1}-01-01"
    else:
        end = f"{YEAR}-{m+1:02d}-01"
    months.append((start, end))

for start, end in months:
    print(f"=== {start} ~ {end} ===")
    start_ts = main.parse_time(start, is_end=False)
    end_ts = main.parse_time(end, is_end=False)
    
    batch = 1000
    current_time = start_ts
    all_data = []
    
    while current_time < end_ts:
        raw = main.fetch_binance_data(f"{SYMBOL.upper()}USDT", INTERVAL, batch, current_time, None)
        if not raw or len(raw) == 0:
            break
        all_data.extend(raw)
        print(f"  获取 {len(all_data)} 条...")
        current_time = raw[-1][0] + 1
        if len(raw) < batch:
            break
        time.sleep(0.2)
    
    indicators = main.calculate_indicators_for_each_candle(all_data)
    records = [main.create_record(candle, indicators[i]) for i, candle in enumerate(all_data)]
    collection = main.db[f"{SYMBOL}_{INTERVAL}"]
    main.store_records_batch(collection, records)
    print(f"  存储完成: {len(records)} 条")

print("全部完成!")
SCRIPT

./venv/bin/python3 fetch_year.py
```

## Python调用
```python
import sys
sys.path.append('~/.openclaw/workspaces/ross/skills/trading_data')
from main import get_recent_records

# 获取最近10条数据
records = get_recent_records("btc", "5m", 10)
for r in records:
    print(r)
```

## Collection命名规则
`{symbol}_{interval}` 例如: `btc_5m`, `eth_1h`, `sol_15m`

## 支持的币种
**任意Binance支持的币种** (通过normalize_symbol自动转换)
- btc → BTCUSDT
- eth → ETHUSDT
- sol → SOLUSDT
- bnb → BNBUSDT

---

# 经验总结 (重要!)

## 获取历史数据常见问题

### 1. Binance API 限制
- **每次最多返回1000条**
- 需要循环获取，用最后一条时间+1作为下次起始时间
- **重要**: 不要传endTime参数，只用startTime，让API返回从startTime往后的数据

### 2. 时间解析
- 开始时间: parse_time("2025-01-01") → 2025-01-01 00:00:00 UTC
- 结束时间: parse_time("2025-01-31", is_end=True) → 2025-01-31 23:59:59 UTC

### 3. 数据量估算
- 5m: 每年约105,000条 (288条/天)
- 15m: 每年约35,000条 (96条/天)
- 1h: 每年约8,760条

### 4. 完整获取一年数据的步骤
1. 清空旧数据: `db.drop_collection('sol_5m')`
2. 使用专用脚本按月循环获取
3. 每批请求间隔0.2秒避免限流
4. 验证数据完整性 (5m一年约10.5万条)

### 5. 调试技巧
- 先用小数据量测试: `--limit 100`
- 查看已有数据量: `db.collection.count_documents({})`
- 查看时间范围: `db.collection.find().sort('time', 1/ -1)`
