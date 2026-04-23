# TOOLS.md - 工具笔记

## Skill 安装规范

安装任何 skill 前，先读它的 `SKILL.md`，确认是否带 hook：
- **带 hook 的 skill**（如 self-improving-agent）→ 安装后必须执行 `openclaw hooks enable <hook名>`，否则该 skill 不会主动触发
- **不带 hook 的 skill**（如 ui-ux-pro-max）→ 直接加载 SKILL.md 即可
