def calculate_tech_indicators(data):
    """计算RSI/KDJ/BOLL/EMA指标"""
    if not data:
        return {
            'rsi': 50.0,
            'kdj': {'k': 50.0, 'd': 50.0, 'j': 50.0},
            'boll': {'upper': 0, 'middle': 0, 'lower': 0},
            'ema': {'ema9': 0, 'ema21': 0}
        }
    
    # 提取收盘价序列
    closes = [float(candle[4]) for candle in data]
    highs = [float(candle[2]) for candle in data]
    lows = [float(candle[3]) for candle in data]
    
    # 计算RSI (简单14周期)
    n = 14
    if len(closes) >= n:
        gains = []
        losses = []
        for i in range(1, len(closes)):
            change = closes[i] - closes[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        avg_gain = sum(gains[-n:]) / n
        avg_loss = sum(losses[-n:]) / n
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
    else:
        rsi = 50.0
    
    # 计算KDJ (简单版本)
    k, d = 50.0, 50.0
    if len(closes) >= 9:
        lowest = min(closes[-9:])
        highest = max(closes[-9:])
        if highest != lowest:
            rsv = (closes[-1] - lowest) / (highest - lowest) * 100
        else:
            rsv = 50
        k = 2/3 * d + 1/3 * rsv
        d = 2/3 * d + 1/3 * k
    j = 3 * k - 2 * d
    
    # 计算BOLL (20周期)
    period = 20
    if len(closes) >= period:
        recent_closes = closes[-period:]
        middle = sum(recent_closes) / period
        std = (sum((x - middle) ** 2 for x in recent_closes) / period) ** 0.5
        upper = middle + 2 * std
        lower = middle - 2 * std
    else:
        middle = sum(closes) / len(closes)
        upper = middle * 1.02
        lower = middle * 0.98
    
    # 计算EMA (9周期和21周期)
    def calc_ema(prices, period):
        if len(prices) < period:
            return prices[-1] if prices else 0
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        return ema
    
    ema9 = calc_ema(closes, 9)
    ema21 = calc_ema(closes, 21)
    
    return {
        'rsi': round(rsi, 2),
        'kdj': {'k': round(k, 2), 'd': round(d, 2), 'j': round(j, 2)},
        'boll': {'upper': round(upper, 2), 'middle': round(middle, 2), 'lower': round(lower, 2)},
        'ema': {'ema9': round(ema9, 2), 'ema21': round(ema21, 2)}
    }
