import os
import time
import pymongo
import requests
from datetime import datetime
import sys
import argparse
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from reference.indicators import calculate_tech_indicators

# Binance API配置
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET')
BINANCE_URL = 'https://api.binance.com/api/v3/klines'

# MongoDB连接
client = pymongo.MongoClient(os.getenv('MONGO_URL', os.getenv('MONGO_URI', 'mongodb://localhost:27017/')))
db = client['trading-data']

# Symbol映射
SYMBOL_MAP = {
    "btc": "BTCUSDT",
    "eth": "ETHUSDT",
    "bnb": "BNBUSDT"
}

# 数据结构：每条记录包含 price, qty, time, rsi, kdj, boll
def create_record(candle, tech_indicators):
    """
    创建单条记录
    candle: [open_time, open, high, low, close, volume, ...]
    tech_indicators: {'rsi': x, 'kdj': {...}, 'boll': {...}}
    """
    return {
        "price": float(candle[4]),      # 收盘价
        "qty": float(candle[5]),         # 成交量
        "time": int(candle[0]),          # K线开始时间
        "rsi": tech_indicators.get('rsi'),
        "kdj": tech_indicators.get('kdj', {}),
        "boll": tech_indicators.get('boll', {})
    }

# 获取K线数据
def fetch_binance_data(symbol, interval='1h', limit=50):
    params = {
        'symbol': symbol,
        'interval': interval,
        'limit': limit
    }
    headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
    
    try:
        response = requests.get(BINANCE_URL, params=params, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API请求失败: {e}")
        return False

# 存储单条记录到MongoDB
def store_record(collection, record):
    try:
        collection.insert_one(record)
        print(f"数据已存储: price={record['price']}, time={record['time']}")
    except Exception as e:
        print(f"存储失败: {e}")

# 批量存储记录
def store_records_batch(collection, records):
    try:
        if records:
            collection.insert_many(records)
            print(f"批量存储 {len(records)} 条记录完成")
    except Exception as e:
        print(f"批量存储失败: {e}")

# 获取最近10条数据
def get_recent_records(symbol, interval='5m', limit=10):
    """
    获取指定交易对的最近N条记录
    表名格式: btc_5m, eth_1h 等
    """
    collection = db[f"{symbol}_{interval}"]
    try:
        records = list(collection.find()
                       .sort('time', pymongo.DESCENDING)
                       .limit(limit))
        for record in records:
            record.pop('_id', None)
        return records
    except Exception as e:
        print(f"获取数据失败: {e}")
        return []

# 主运行函数
def main():
    parser = argparse.ArgumentParser(description='获取加密货币K线数据')
    parser.add_argument('--symbol', type=str, required=True, help='币种: btc, eth, bnb')
    parser.add_argument('--interval', type=str, default='5m', help='K线周期: 5m, 15m, 1h, 4h, 1d')
    parser.add_argument('--limit', type=int, default=50, help='获取K线数量')
    args = parser.parse_args()
    
    symbol = args.symbol.lower()
    interval = args.interval
    
    # 验证币种
    if symbol not in SYMBOL_MAP:
        print(f"不支持的币种: {symbol}")
        print(f"支持的币种: {list(SYMBOL_MAP.keys())}")
        return
    
    binance_symbol = SYMBOL_MAP[symbol]
    
    # 获取原始数据
    raw_data = fetch_binance_data(binance_symbol, interval, args.limit)
    if not raw_data:
        print(f"获取 {binance_symbol} 数据失败")
        return
    
    # 计算技术指标
    tech_indicators = calculate_tech_indicators(raw_data)
    
    # 为每根K线创建记录
    records = []
    for candle in raw_data:
        record = create_record(candle, tech_indicators)
        records.append(record)
    
    # 存储到MongoDB
    collection = db[f"{symbol}_{interval}"]
    store_records_batch(collection, records)
    
    # 打印最近10条数据
    print(f"\n=== {symbol.upper()} {interval} 最近10条数据 ===")
    recent = get_recent_records(symbol, interval, 10)
    for r in recent:
        print(r)
    
    print(f"\n数据获取完成")

if __name__ == "__main__":
    main()
