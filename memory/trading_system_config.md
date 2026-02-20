# 洛氏霍克交易系统 - 重要配置

## 数据查询规则

**优先级：本地MongoDB > Binance API**

- 查询交易数据时，先从本地 `trading-data` 数据库查询
- 如果查询的时间范围内没有数据，再通过 Binance API 获取
- **通过API获取的数据，必须保存到数据库**
- 数据表：`trading-data.btc_5m`

## 数据字段

每条K线记录包含：
- `price`: 收盘价
- `qty`: 成交量
- `time`: K线时间戳
- `rsi`: RSI指标
- `kdj`: K/D/J值
- `boll`: BOLL上/中/下轨
- `ema`: EMA9 / EMA21

## 当前数据状态

- 数据量：2000条
- 时间范围：2026-02-02 ~ 2026-02-20
- 更新频率：按需更新
