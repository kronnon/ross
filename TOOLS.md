# TOOLS.md - 工具笔记

## Web Search

**平台：Tavily**（直接调 API，不用 `web_search` 工具）

调用方式（exec）：
```bash
curl -s -X POST https://api.tavily.com/search \
  -H "Content-Type: application/json" \
  -d '{"api_key":"'"$TAVILY_API_KEY"'","query":"<搜索词>","search_depth":"basic","max_results":5}'
```

**注意：**
- API Key 在 `~/.openclaw/.env`：`TAVILY_API_KEY`
- 优先用 `web_fetch` 自己找 URL 抓取；需要搜索时用上面的 curl 命令调 Tavily

## Skill 安装规范

安装任何 skill 前，先读它的 `SKILL.md`，确认是否带 hook：
- **带 hook 的 skill**（如 self-improving-agent）→ 安装后必须执行 `openclaw hooks enable <hook名>`，否则该 skill 不会主动触发
- **不带 hook 的 skill**（如 ui-ux-pro-max）→ 直接加载 SKILL.md 即可
