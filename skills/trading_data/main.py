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

def parse_time(time_str):
    """解析时间字符串为毫秒时间戳"""
    if not time_str:
        return None
    # 如果是数字，直接返回(假设是毫秒)
    if time_str.isdigit():
        return int(time_str)
    # 尝试解析 YYYY-MM-DD 格式
    try:
        from datetime import datetime, timezone
        dt = datetime.strptime(time_str, '%Y-%m-%d')
        return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
    except:
        return None

# 数据结构：每条记录包含 price, qty, time, rsi, kdj, boll, ema
def create_record(candle, tech_indicators):
    """
    创建单条记录
    candle: [open_time, open, high, low, close, volume, ...]
    tech_indicators: {'rsi': x, 'kdj': {...}, 'boll': {...}, 'ema': {...}}
    """
    return {
        "price": float(candle[4]),      # 收盘价
        "qty": float(candle[5]),         # 成交量
        "time": int(candle[0]),          # K线开始时间
        "rsi": tech_indicators.get('rsi'),
        "kdj": tech_indicators.get('kdj', {}),
        "boll": tech_indicators.get('boll', {}),
        "ema": tech_indicators.get('ema', {})
    }

# 计算每根K线的技术指标
def calculate_indicators_for_each_candle(data):
    """
    为每根K线计算技术指标
    返回每根K线对应的指标字典列表
    """
    if not data:
        return []
    
    # 提取收盘价、最高价、最低价序列
    closes = [float(candle[4]) for candle in data]
    highs = [float(candle[2]) for candle in data]
    lows = [float(candle[3]) for candle in data]
    
    indicators_list = []
    
    for i in range(len(closes)):
        # 计算RSI (需要至少14根K线)
        rsi = None
        if i >= 14:
            n = 14
            gains = []
            losses = []
            for j in range(i - n + 1, i + 1):
                change = closes[j] - closes[j-1] if j > 0 else 0
                gains.append(change if change > 0 else 0)
                losses.append(abs(change) if change < 0 else 0)
            avg_gain = sum(gains) / n
            avg_loss = sum(losses) / n
            if avg_loss == 0:
                rsi = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi = round(100 - (100 / (1 + rs)), 2)
        
        # 计算KDJ (需要至少9根K线)
        kdj = {'k': None, 'd': None, 'j': None}
        if i >= 9:
            lowest = min(lows[i-8:i+1])
            highest = max(highs[i-8:i+1])
            if highest != lowest:
                rsv = (closes[i] - lowest) / (highest - lowest) * 100
            else:
                rsv = 50
            k = 2/3 * 50 + 1/3 * rsv
            d = 2/3 * 50 + 1/3 * k
            j = 3 * k - 2 * d
            kdj = {'k': round(k, 2), 'd': round(d, 2), 'j': round(j, 2)}
        
        # 计算BOLL (需要至少20根K线)
        boll = {'upper': None, 'middle': None, 'lower': None}
        if i >= 20:
            period = 20
            recent_closes = closes[i-period+1:i+1]
            middle = sum(recent_closes) / period
            std = (sum((x - middle) ** 2 for x in recent_closes) / period) ** 0.5
            upper = middle + 2 * std
            lower = middle - 2 * std
            boll = {'upper': round(upper, 2), 'middle': round(middle, 2), 'lower': round(lower, 2)}
        
        # 计算EMA (需要至少21根K线)
        ema = {'ema9': None, 'ema21': None}
        if i >= 21:
            def calc_ema(prices, period):
                multiplier = 2 / (period + 1)
                ema_val = sum(prices[:period]) / period
                for price in prices[period:]:
                    ema_val = (price - ema_val) * multiplier + ema_val
                return ema_val
            ema9 = calc_ema(closes[:i+1], 9)
            ema21 = calc_ema(closes[:i+1], 21)
            ema = {'ema9': round(ema9, 2), 'ema21': round(ema21, 2)}
        
        indicators_list.append({
            'rsi': rsi,
            'kdj': kdj,
            'boll': boll,
            'ema': ema
        })
    
    return indicators_list
def fetch_binance_data(symbol, interval='1h', limit=50, startTime=None, endTime=None):
    params = {
        'symbol': symbol,
        'interval': interval,
        'limit': limit
    }
    if startTime:
        params['startTime'] = startTime
    if endTime:
        params['endTime'] = endTime
    headers = {'X-MBX-APIKEY': BINANCE_API_KEY} if BINANCE_API_KEY else {}
    
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
    parser.add_argument('--start', type=str, default=None, help='开始时间: YYYY-MM-DD 或 timestamp(ms)')
    parser.add_argument('--end', type=str, default=None, help='结束时间: YYYY-MM-DD 或 timestamp(ms)')
    args = parser.parse_args()
    
    symbol = args.symbol.lower()
    interval = args.interval
    
    # 验证币种
    if symbol not in SYMBOL_MAP:
        print(f"不支持的币种: {symbol}")
        print(f"支持的币种: {list(SYMBOL_MAP.keys())}")
        return
    
    # 解析时间参数
    start_time = None
    end_time = None
    if args.start:
        start_time = parse_time(args.start)
    if args.end:
        end_time = parse_time(args.end)
    
    binance_symbol = SYMBOL_MAP[symbol]
    
    # 获取原始数据
    raw_data = fetch_binance_data(binance_symbol, interval, args.limit, start_time, end_time)
    if not raw_data:
        print(f"获取 {binance_symbol} 数据失败")
        return
    
    # 为每根K线计算技术指标
    indicators_list = calculate_indicators_for_each_candle(raw_data)
    
    # 为每根K线创建记录
    records = []
    for i, candle in enumerate(raw_data):
        record = create_record(candle, indicators_list[i])
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
