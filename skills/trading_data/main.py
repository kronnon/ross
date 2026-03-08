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

# Symbol映射 - 支持任意币种
# 用户输入如 "btc" -> "BTCUSDT", "sol" -> "SOLUSDT"
SYMBOL_MAP = {
    "btc": "BTCUSDT",
    "eth": "ETHUSDT",
    "bnb": "BNBUSDT"
}

def normalize_symbol(symbol):
    """将用户输入的币种标准化为Binance交易对格式"""
    symbol = symbol.upper()
    # 已经是完整交易对格式 (如 BTCUSDT)
    if symbol.endswith('USDT') or symbol.endswith('USDTC'):
        return symbol
    # 基础币种格式 (如 BTC, ETH, SOL)
    return f"{symbol}USDT"

def parse_time(time_str, is_end=False):
    """解析时间字符串为毫秒时间戳"""
    if not time_str:
        return None
    # 如果是数字，直接返回(假设是毫秒)
    if time_str.isdigit():
        return int(time_str)
    # 尝试解析 YYYY-MM-DD 格式
    try:
        from datetime import datetime, timezone, timedelta
        dt = datetime.strptime(time_str, '%Y-%m-%d')
        if is_end:
            # 结束时间设为当天的23:59:59
            dt = dt + timedelta(days=1) - timedelta(seconds=1)
        return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
    except:
        return None

# 数据结构：每条记录包含 open, high, low, close, qty, time, rsi, kdj, boll, ema
def create_record(candle, tech_indicators):
    """
    创建单条记录
    candle: [open_time, open, high, low, close, volume, ...]
    tech_indicators: {'rsi': x, 'kdj': {...}, 'boll': {...}, 'ema': {...}}
    """
    return {
        "open": float(candle[1]),        # 开盘价
        "high": float(candle[2]),        # 最高价
        "low": float(candle[3]),         # 最低价
        "close": float(candle[4]),       # 收盘价
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
def fetch_binance_data(symbol, interval='1h', limit=50, startTime=None, endTime=None, retries=3):
    """获取Binance数据，带重试机制"""
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
    
    for attempt in range(retries):
        try:
            response = requests.get(BINANCE_URL, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"API请求失败 (尝试 {attempt+1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(1)  # 等待后重试
            else:
                return False
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

# 数据完整性检查
def check_data_integrity(symbol, interval, start_time=None, end_time=None):
    """
    检查数据的完整性和连续性
    """
    collection = db[f"{symbol}_{interval}"]
    
    # 获取总数据量
    total_count = collection.count_documents({})
    print(f"\n=== 数据完整性检查 ===")
    print(f"总数据量: {total_count} 条")
    
    # 获取时间范围
    earliest = collection.find().sort('time', 1).limit(1)[0]
    latest = collection.find().sort('time', -1).limit(1)[0]
    
    print(f"最早时间: {earliest['time']} ({datetime.fromtimestamp(earliest['time']/1000).strftime('%Y-%m-%d %H:%M:%S')})")
    print(f"最晚时间: {latest['time']} ({datetime.fromtimestamp(latest['time']/1000).strftime('%Y-%m-%d %H:%M:%S')})")
    
    # 计算时间间隔
    time_range_ms = latest['time'] - earliest['time']
    days = time_range_ms / (1000 * 60 * 60 * 24)
    print(f"时间跨度: {days:.1f} 天")
    
    # 间隔映射
    interval_ms = {
        '1m': 60000, '3m': 180000, '5m': 300000, '15m': 900000,
        '30m': 1800000, '1h': 3600000, '2h': 7200000, '4h': 14400000,
        '6h': 21600000, '8h': 28800000, '12h': 43200000,
        '1d': 86400000, '1w': 604800000
    }
    
    expected_interval = interval_ms.get(interval, 300000)
    expected_count = time_range_ms // expected_interval + 1
    missing = expected_count - total_count
    
    print(f"预期数据量: ~{expected_count} 条 (基于时间跨度)")
    print(f"实际数据量: {total_count} 条")
    print(f"缺失/多余: {missing:+d} 条")
    
    if missing > 0:
        print(f"⚠️  警告: 缺少约 {missing} 条数据")
    elif missing < -100:
        print(f"⚠️  警告: 多出约 {-missing} 条数据(可能存在重复)")
    else:
        print(f"✅ 数据完整")
    
    # 抽样检查连续性（检查100个间隔）
    print(f"\n=== 连续性检查 ===")
    sample_size = min(100, total_count - 1)
    if sample_size > 0:
        # 获取均匀分布的样本
        step = max(1, total_count // sample_size)
        pipeline = [
            {'$sort': {'time': 1}},
            {'$skip': 0},
            {'$limit': total_count},
            {'$group': {
                '_id': {'$mod': [step, {'$sum': [1, {'$divide': ['$time', expected_interval]}]}]},
                'count': {'$sum': 1}
            }}
        ]
        
        # 简单方法：随机检查一些间隔
        gaps = 0
        abnormal_gaps = 0
        records = list(collection.find().sort('time', 1).limit(1000))
        
        for i in range(len(records) - 1):
            gap = records[i+1]['time'] - records[i]['time']
            if gap != expected_interval:
                abnormal_gaps += 1
                if abs(gap - expected_interval) > expected_interval * 2:
                    gaps += 1
        
        abnormal_pct = abnormal_gaps / len(records) * 100 if records else 0
        print(f"检查前1000条数据:")
        print(f"  异常间隔数: {abnormal_gaps} ({abnormal_pct:.1f}%)")
        
        if gaps > 0:
            print(f"  ⚠️  存在较大间隔缺失")
        else:
            print(f"  ✅ 连续性良好")

# 主运行函数
def main():
    parser = argparse.ArgumentParser(description='获取加密货币K线数据')
    parser.add_argument('--symbol', type=str, required=True, help='币种: btc, eth, bnb')
    parser.add_argument('--interval', type=str, default='5m', help='K线周期: 5m, 15m, 1h, 4h, 1d')
    parser.add_argument('--limit', type=int, default=50, help='获取K线数量(默认50)')
    parser.add_argument('--max', type=int, default=None, help='最大获取数量(用于历史数据)')
    parser.add_argument('--start', type=str, default=None, help='开始时间: YYYY-MM-DD 或 timestamp(ms)')
    parser.add_argument('--end', type=str, default=None, help='结束时间: YYYY-MM-DD 或 timestamp(ms)')
    args = parser.parse_args()
    
    symbol = args.symbol.lower()
    interval = args.interval
    
    # 使用normalize_symbol处理任意币种
    binance_symbol = normalize_symbol(symbol)
    
    # 解析时间参数
    start_time = None
    end_time = None
    if args.start:
        start_time = parse_time(args.start, is_end=False)
    if args.end:
        end_time = parse_time(args.end, is_end=True)
    
    # 如果指定了时间范围，循环获取所有数据
    max_count = args.max or args.limit
    all_raw_data = []
    
    if start_time and end_time:
        # 时间范围模式：循环获取（每次最多1000条）
        print(f"获取 {binance_symbol} {interval} 数据 ({args.start} ~ {args.end})...")
        
        # 检查已存在的数据，避免重复获取
        collection = db[f"{symbol}_{interval}"]
        existing_count = collection.count_documents({})
        
        # 默认从start_time开始
        current_time = start_time
        
        if existing_count > 0:
            # 获取已有数据的最早和最晚时间
            earliest = collection.find().sort('time', 1).limit(1)[0]
            latest = collection.find().sort('time', -1).limit(1)[0]
            print(f"已有数据: {existing_count} 条, 时间范围: {earliest['time']} ~ {latest['time']}")
            
            # 如果已有数据覆盖目标范围，就跳过
            if earliest['time'] <= start_time and latest['time'] >= end_time:
                print("数据已完整，跳过获取")
                # 直接进行完整性检查然后返回
                check_data_integrity(symbol, interval, start_time, end_time)
                print(f"\n数据获取完成")
                return
            else:
                # 增量获取：从最新数据之后开始
                current_time = latest['time'] + 300000  # 加5分钟
                print(f"增量获取从 {current_time} 开始...")
        
        batch = 1000  # Binance API每次最多返回1000条
        collection = db[f"{symbol}_{interval}"]  # 提前创建collection对象
        
        while current_time < end_time:
            # 关键：不传endTime，让API从startTime往后返回最多1000条
            raw = fetch_binance_data(binance_symbol, interval, batch, current_time, None)
            if not raw or len(raw) == 0:
                print("API返回空数据，停止获取")
                break
            
            # 立即处理并保存这批数据（增量保存）
            indicators_list = calculate_indicators_for_each_candle(raw)
            records = []
            for i, candle in enumerate(raw):
                record = create_record(candle, indicators_list[i])
                records.append(record)
            
            # 立即存储到MongoDB
            store_records_batch(collection, records)
            
            all_raw_data.extend(raw)
            print(f"已获取并保存 {len(all_raw_data)} 条, 最新时间: {raw[-1][0]}...")
            
            # 更新起始时间：用最后一条数据的时间+1ms作为下次起始时间
            current_time = raw[-1][0] + 1
            
            # 如果返回数据少于batch条，说明已经到头了
            if len(raw) < batch:
                print("数据已全部获取完成")
                break
            
            # 如果已达到max_count限制
            if max_count and len(all_raw_data) >= max_count:
                print(f"已达到最大数量限制 {max_count}")
                all_raw_data = all_raw_data[:max_count]
                break
            
            time.sleep(0.3)  # 降低API请求频率，避免被限流
        
        raw_data = all_raw_data
    else:
        # 简单模式：直接获取最近的数据
        raw_data = fetch_binance_data(binance_symbol, interval, args.limit, start_time, end_time)
    
    if not raw_data:
        print(f"获取 {binance_symbol} 数据失败")
        return
    
    # 简单模式或非增量模式的数据存储（已在上方处理）
    if not (start_time and end_time):
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
    
    # 数据完整性检查
    check_data_integrity(symbol, interval, start_time, end_time)
    
    print(f"\n数据获取完成")

if __name__ == "__main__":
    main()
