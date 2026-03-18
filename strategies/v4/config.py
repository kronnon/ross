"""
配置管理模块

配置由量化系统维护，策略只负责读取
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass, fields


@dataclass
class StrategyConfig:
    """策略配置类 - 所有参数由外部量化系统传入"""
    
    # === 基础参数 ===
    leverage: int = 10                    # 杠杆倍数
    initial_balance: float = 100.0        # 初始余额
    
    # === 交易间隔 ===
    min_trade_interval: int = 3           # 最小交易间隔（K线数）
    max_hold_bars: int = 288              # 最大持仓K线数
    
    # === 止损止盈 ===
    stop_loss_pct: float = 5.0            # 止损比例 %
    take_profit_pct: float = 2.0          # 止盈比例 %
    
    # === 以损定仓 ===
    risk_pct: float = 1.0                 # 风险比例 %
    max_position: float = 500.0           # 最大仓位上限
    use_position_size_mode: bool = False  # True=固定仓位, False=以损定仓
    
    # === 形态识别 ===
    lookback_bars: int = 10               # 回看K线数
    min_thrust: float = 0.3               # 最小突破幅度%
    p2_p3_lookback: int = 5              # P2/P3回看范围（K线数）
    
    # === 多仓位 ===
    max_concurrent_positions: int = 3     # 最大同时持仓数
    
    # === 真实交易模拟 ===
    slippage_pct: float = 0.1             # 滑点百分比
    fill_rate: float = 0.9                # 成交率
    commission_rate: float = 0.04         # 手续费率 %
    min_volume: float = 1000               # 最小成交量过滤
    
    # === 风险管理（增强）===
    # 移动止损
    enable_trailing_stop: bool = False     # 开启移动止损
    trailing_stop_pct: float = 0.0        # 移动止损触发盈利%
    
    # 分批止盈
    enable_partial_tp: bool = False        # 开启分批止盈
    partial_tp_pct: float = 0.0           # 分批止盈触发盈利%
    
    # ATR止损
    enable_atr_stop: bool = False          # 开启ATR止损
    atr_period: int = 14                  # ATR周期
    atr_multiplier: float = 2.0            # ATR倍数
    
    # === RSI过滤 ===
    enable_rsi_filter: bool = False        # 开启RSI过滤
    rsi_period: int = 14                  # RSI周期
    rsi_overbought: float = 70             # RSI超买阈值
    rsi_oversold: float = 30               # RSI超卖阈值
    
    # === 多周期确认 ===
    # 有值则开启多周期确认，无值则不开启
    higher_timeframe: str = ''              # 大级别周期，如'15m'、'1h'，空字符串=不开启
    ht_lookback: int = 50                  # 大周期回看K线数
    
    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'StrategyConfig':
        """
        从字典创建配置（由量化系统调用）
        
        Args:
            config: 包含所有必需参数的字典
        
        Returns:
            StrategyConfig实例
        """
        # 检查必需参数
        required_fields = {
            'leverage', 'initial_balance', 'min_trade_interval', 'max_hold_bars',
            'stop_loss_pct', 'take_profit_pct', 'risk_pct', 'max_position',
            'use_position_size_mode', 'lookback_bars', 'min_thrust',
            'max_concurrent_positions', 'slippage_pct', 'fill_rate',
            'commission_rate', 'min_volume'
        }
        
        missing = required_fields - set(config.keys())
        if missing:
            raise ValueError(f"缺少必需配置参数: {missing}")
        
        return cls(**{k: v for k, v in config.items() if k in {f.name for f in fields(cls)}})
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（供量化系统读取）"""
        return {
            'leverage': self.leverage,
            'initial_balance': self.initial_balance,
            'min_trade_interval': self.min_trade_interval,
            'max_hold_bars': self.max_hold_bars,
            'stop_loss_pct': self.stop_loss_pct,
            'take_profit_pct': self.take_profit_pct,
            'risk_pct': self.risk_pct,
            'max_position': self.max_position,
            'use_position_size_mode': self.use_position_size_mode,
            'lookback_bars': self.lookback_bars,
            'min_thrust': self.min_thrust,
            'p2_p3_lookback': self.p2_p3_lookback,
            'max_concurrent_positions': self.max_concurrent_positions,
            'slippage_pct': self.slippage_pct,
            'fill_rate': self.fill_rate,
            'commission_rate': self.commission_rate,
            'min_volume': self.min_volume,
            'enable_trailing_stop': self.enable_trailing_stop,
            'trailing_stop_pct': self.trailing_stop_pct,
            'enable_partial_tp': self.enable_partial_tp,
            'partial_tp_pct': self.partial_tp_pct,
            'enable_atr_stop': self.enable_atr_stop,
            'atr_period': self.atr_period,
            'atr_multiplier': self.atr_multiplier,
            'enable_rsi_filter': self.enable_rsi_filter,
            'rsi_period': self.rsi_period,
            'rsi_overbought': self.rsi_overbought,
            'rsi_oversold': self.rsi_oversold,
            'higher_timeframe': self.higher_timeframe,
            'ht_lookback': self.ht_lookback,
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项（兼容dict方式访问）"""
        return getattr(self, key, default)
    
    def __getitem__(self, key: str) -> Any:
        """支持dict方式访问"""
        return getattr(self, key)
    
    def __setitem__(self, key: str, value: Any):
        """支持dict方式设置"""
        setattr(self, key, value)
    
    def validate(self) -> bool:
        """验证配置有效性"""
        if self.leverage <= 0:
            raise ValueError("leverage 必须 > 0")
        if self.initial_balance <= 0:
            raise ValueError("initial_balance 必须 > 0")
        if self.stop_loss_pct <= 0 or self.take_profit_pct <= 0:
            raise ValueError("止损/止盈必须 > 0")
        if self.risk_pct <= 0:
            raise ValueError("risk_pct 必须 > 0")
        return True
    
    @classmethod
    def reload_from_db(cls, db, version: str = "latest") -> 'StrategyConfig':
        """
        从MongoDB重新加载配置（热更新）
        
        Args:
            db: MongoDB数据库实例
            version: 配置版本号，如 "v4.0.0" 或 "latest"
        
        Returns:
            StrategyConfig实例
        """
        collection = db['strategies']['versions']
        
        # 查找指定版本或最新版本
        if version == "latest":
            config_doc = collection.find_one(sort=[("version", -1)])
        else:
            config_doc = collection.find_one({"version": version})
        
        if not config_doc:
            raise ValueError(f"未找到版本配置: {version}")
        
        return cls.from_dict(config_doc['params'])


# ==================== 配置管理工具 ====================

class ConfigManager:
    """配置管理器 - 用于量化系统"""
    
    def __init__(self, db):
        self.db = db
        self.collection = db['strategies']['versions']
        self._current_config = None
    
    def load(self, version: str = "latest") -> StrategyConfig:
        """加载配置"""
        self._current_config = StrategyConfig.reload_from_db(self.db, version)
        return self._current_config
    
    def reload(self, version: str = None) -> StrategyConfig:
        """重新加载配置"""
        if version is None:
            # 重新加载当前版本
            if self._current_config is None:
                raise ValueError("未加载配置，请先调用load()")
            # 获取当前版本号
            current = self.collection.find_one({"params": self._current_config.to_dict()})
            if current:
                version = current['version']
            else:
                version = "latest"
        
        self._current_config = StrategyConfig.reload_from_db(self.db, version)
        return self._current_config
    
    def get_current(self) -> StrategyConfig:
        """获取当前配置"""
        if self._current_config is None:
            raise ValueError("未加载配置，请先调用load()")
        return self._current_config
    
    def list_versions(self) -> list:
        """列出所有可用版本"""
        return list(self.collection.find({}, {"version": 1, "name": 1, "updated_at": 1}))


# ==================== 量化系统调用示例 ====================

"""
# 量化系统配置示例

# 1. 定义配置（由量化系统维护）
my_config = {
    'leverage': 10,
    'initial_balance': 10000,
    'min_trade_interval': 3,
    'max_hold_bars': 288,
    'stop_loss_pct': 5.0,
    'take_profit_pct': 2.0,
    'risk_pct': 1.0,
    'max_position': 500,
    'use_position_size_mode': False,
    'lookback_bars': 10,
    'min_thrust': 0.3,
    'max_concurrent_positions': 3,
    'slippage_pct': 0.1,
    'fill_rate': 0.9,
    'commission_rate': 0.04,
    'min_volume': 1000,
    
    # 风险管理开关
    'enable_trailing_stop': True,
    'trailing_stop_pct': 3.0,
    'enable_partial_tp': True,
    'partial_tp_pct': 1.5,
    'enable_atr_stop': False,
    'atr_period': 14,
    'atr_multiplier': 2.0,
    
    # 过滤器开关
    'enable_rsi_filter': True,
    'rsi_overbought': 70,
    'rsi_oversold': 30,
}

# 2. 创建策略配置
config = StrategyConfig.from_dict(my_config)

# 3. 传入策略
from v4 import BacktestEngine
engine = BacktestEngine(config)
"""
