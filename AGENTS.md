# AGENTS.md - ross 的工作区

这是 ross 的专属工作区。每次会话先读 `SOUL.md`、`USER.md`、`memory/`。

## 语言
中文

## 工作方式
- 任务拆解 → 小任务逐一汇报
- 回复简洁，只在关键节点出结果
- 输出文件存 `outputs/`

## 工具：trading_data
数据获取用 `~/.openclaw/workspaces/ross/skills/trading_data/`

**命令示例：**
```bash
cd ~/.openclaw/workspaces/ross/skills/trading_data
./venv/bin/python3 main.py --symbol btc --interval 5m --limit 1000
```

---

> 文档太大？安全/记忆细节已抽到 `memory/` 目录，按需加载。
