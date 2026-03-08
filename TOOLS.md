# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## 工作区目录结构

- `strategies/` - 策略代码文件夹
- `outputs/` - 输出结果文件夹（交易记录、统计报表等）

## 回测流程 (重要!)

### 输出目录
- 所有回测输出文件统一保存在 `outputs/` 文件夹

### 每次回测必须输出的文档

1. **Excel交易记录** - 必有
   - 位置: `outputs/ross_trading_v38_{symbol}_{interval}_trades.xlsx`
   - 格式: 包含序号、方向、入/出场时间、价格、持仓K线数、仓位、计划止损/止盈、出场原因、盈亏金额/百分比、余额

2. **Markdown回测报告** - 推荐
   - 位置: `outputs/{symbol}_{year}_backtest_report.md`
   - 内容: 回测参数、数据量、交易次数、胜率、总盈亏、出场分析、结论建议

### 回测命令

```bash
cd ~/.openclaw/workspaces/ross/strategies

# 回测5m数据
~/.openclaw/workspaces/ross/skills/trading_data/venv/bin/python3 ross_trading_v38.py --symbol sol --interval 5m

# 回测15m数据
~/.openclaw/workspaces/ross/skills/trading_data/venv/bin/python3 ross_trading_v38.py --symbol sol --interval 15m
```

### 回测前检查

- 确保MongoDB中有足够的历史数据
- 检查CONFIG参数是否正确（position_size, leverage, stop_loss_pct, take_profit_pct）
- 确认策略脚本无bug（如参数名统一）

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.
