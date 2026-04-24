"""
配置管理模块 v5

配置由量化系统维护，策略只负责读取

v5 更新：
- 新增：max_total_position（总仓位上限）
- 新增：fixed_loss（固定亏损额，替代 risk_pct）
- 新增：position_size（固定仓位金额）
- 新增：形态识别精细参数（max_lookback, pattern_lookback 等）
- 新增：KDJ/BOLL/EMA 过滤器参数
- 新增：max_daily_loss（每日最大亏损）
- 新增：trigger_timeout_bars（触发委托超时）
- 新增：skip_ross_hook（跳过 Ross Hook）
- 新增：risk_pct（百分比以损定仓，与 fixed_loss 二选一）
- 移除：max_concurrent_positions（改用 max_total_position 控制）
"""

from dataclasses import MISSING, dataclass, fields
from typing import Any, Dict


@dataclass
class StrategyConfig:
    """策略配置类 - 所有参数由外部量化系统传入"""

    # === 基础参数 ===
    leverage: int = 10  # 杠杆倍数
    initial_balance: float = 100.0  # 初始余额

    # === 交易间隔 ===
    min_trade_interval: int = 3  # 最小交易间隔（K线数）
    max_hold_bars: int = 288  # 最大持仓K线数

    # === 止损止盈 ===
    stop_loss_pct: float = 5.0  # 止损比例 %
    take_profit_pct: float = 2.0  # 止盈比例 %

    # === 以损定仓（v5 更新）===
    max_position: float = 500.0  # 单次最大仓位上限
    max_total_position: float = 1000.0  # 总仓位上限（所有持仓合计）
    fixed_loss: float = 2.0  # 固定亏损额 USDT（fixed_loss > 0 时生效，优先级高于 risk_pct）
    risk_pct: float = 0.0  # 风险百分比 %（仓位 = 余额 × risk_pct% / 止损%，fixed_loss = 0 时生效）
    use_position_size_mode: bool = False  # True=固定仓位, False=以损定仓
    position_size: float = 100.0  # 固定仓位金额（固定仓位模式时生效）USDT


    # === 形态识别（v5 精细化）===
    lookback_bars: int = 10  # 回看K线数
    min_thrust: float = 0.3  # 最小突破幅度%
    p2_p3_lookback: int = 5  # P2/P3回看范围（K线数）
    breakout_lookahead: int = 3  # Hook后几根K线内确认突破（默认3）

    # === 1-2-3形态精细参数（v5 新增）===
    max_lookback: int = 10  # P1回看范围（往前多少根K线找P1）
    pattern_lookback: int = 2  # P1局部极值判断（前后几根必须比P1低/高）
    min_bars_before_signal: int = 15  # 起信号前最小K线数
    hook_search_range: int = 8  # Ross Hook搜索范围（P3后几根内找Hook）
    confidence_threshold: float = 1.5  # 置信度满分门槛（%）
    skip_ross_hook: bool = False  # 跳过 Ross Hook，直接用 P3 入场

    # === 真实交易模拟 ===
    slippage_pct: float = 0.1  # 滑点百分比
    fill_rate: float = 0.9  # 成交率
    commission_rate: float = 0.04  # 单边手续费率 %（双边收费，实际为0.08%）
    min_volume: float = 1000000  # 最小交易金额 USDT（volume × price）

    # === 风险管理（增强）===

    # 移动止损
    enable_trailing_stop: bool = False  # 开启移动止损
    trailing_stop_pct: float = 0.0  # 移动止损触发盈利%

    # 分批止盈
    enable_partial_tp: bool = False  # 开启分批止盈
    partial_tp_pct: float = 0.0  # 分批止盈触发盈利%

    # ATR止损
    enable_atr_stop: bool = False  # 开启ATR止损
    atr_period: int = 14  # ATR周期
    atr_multiplier: float = 2.0  # ATR倍数

    # === RSI过滤 ===
    enable_rsi_filter: bool = False  # 开启RSI过滤
    rsi_period: int = 14  # RSI周期
    rsi_overbought: float = 70  # RSI超买阈值
    rsi_oversold: float = 30  # RSI超卖阈值

    # === KDJ过滤（v5 新增）===
    enable_kdj_filter: bool = False  # 开启KDJ过滤
    kdj_period: int = 9  # KDJ周期
    kdj_k_overbought: float = 80  # K值超买阈值
    kdj_k_oversold: float = 20  # K值超卖阈值
    kdj_j_overbought: float = 100  # J值超买阈值
    kdj_j_oversold: float = 0  # J值超卖阈值

    # === BOLL过滤（v5 新增）===
    enable_boll_filter: bool = False  # 开启BOLL过滤
    boll_period: int = 20  # BOLL周期
    boll_std: float = 2  # BOLL标准差倍数
    # 做多时价格必须在中轨上方，做空时价格必须在中轨下方

    # === EMA过滤（v5 新增）===
    enable_ema_filter: bool = False  # 开启EMA过滤
    ema_period: int = 20  # EMA周期
    # 做多时价格必须在EMA上方，做空时价格必须在EMA下方

    # === 多周期确认 ===
    # 有值则开启多周期确认，无值则不开启
    higher_timeframe: str = ""  # 大级别周期，如'15m'、'1h'，空字符串=不开启
    ht_lookback: int = 50  # 大周期回看K线数

    # === 每日最大亏损（v5 新增）===
    max_daily_loss: float = 50.0  # 每日最大亏损 USDT

    # === 触发委托超时（v5 新增）===
    trigger_timeout_bars: int = 5  # 触发委托超时K线倍数（K线周期秒 × N = 超时秒数）

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "StrategyConfig":
        """
        从字典创建配置（由量化系统调用）

        Args:
            config: 包含所有必需参数的字典

        Returns:
            StrategyConfig实例
        """
        # 建立字段名→默认值的映射（从 dataclass 字段定义提取）
        field_defaults = {f.name: f.default for f in fields(cls) if f.default is not MISSING}
        # 用默认值填充缺失字段，保证向后兼容（旧配置无新字段时不会报错）
        merged = dict(field_defaults)
        merged.update(config)  # 用户提供的值覆盖默认值

        return cls(**{k: v for k, v in merged.items() if k in {f.name for f in fields(cls)}})

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（供量化系统读取）"""
        from dataclasses import asdict

        return asdict(self)

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
        if self.fixed_loss <= 0:
            raise ValueError("fixed_loss 必须 > 0")
        return True

    @classmethod
    def reload_from_db(cls, db, version: str = "latest") -> "StrategyConfig":
        """
        从MongoDB重新加载配置（热更新）

        Args:
            db: MongoDB数据库实例
            version: 配置版本号，如 "v5.0.0" 或 "latest"

        Returns:
            StrategyConfig实例
        """
        collection = db["strategies"]["versions"]

        # 查找指定版本或最新版本
        if version == "latest":
            config_doc = collection.find_one(sort=[("version", -1)])
        else:
            config_doc = collection.find_one({"version": version})

        if not config_doc:
            raise ValueError(f"未找到版本配置: {version}")

        return cls.from_dict(config_doc["params"])


# ==================== 配置管理工具 ====================


class ConfigManager:
    """配置管理器 - 用于量化系统"""

    def __init__(self, db):
        self.db = db
        self.collection = db["strategies"]["versions"]
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
                version = current["version"]
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
