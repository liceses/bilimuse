# 日志系统 + 统一状态通道 开发日志

- 日期：2026-08-04
- 里程碑：M7
- 关联：PLAN.md M7；[M5 pipeline + TUI](2026-08-04-pipeline-tui.md)、[M6 Web](2026-08-04-web.md)

## 目标与验收

- 目标：① 日志系统（级别区分、生成文件、console WARNING）② 统一状态通道——"系统在做什么"一次产生，UI 显示与日志双写，CLI/TUI/Web 三端动态显示
- 验收标准：
  - `setup_logging` 生成 `<config_dir>/logs/bilimuse.log`（1MB×3 滚动），级别可配
  - `status.emit` 双写：注册的显示回调收到 + 日志文件记录；DEBUG 仅日志
  - 解析元数据/歌词 **provider 级**状态三端可见；config 保存后「已设置 X」；等待输入提示
  - 脱敏：SESSDATA/cookie 不落日志
  - `doctor` 显示日志路径

## 方案与思路

- **日志**：`logging_setup.py`——根 logger `bilimuse`，文件 `RotatingFileHandler`(1MB×3) + console WARNING（用 filter 排除 `bilimuse.status`，避免与 UI echo 重复）。
- **统一状态通道** `status.py`——`emit(level, text)` 双写：写日志（按 level）+ 转发已注册显示回调（INFO+ 才显示，DEBUG 仅日志）。CLI 注册 `_echo_status`。
- **三端动态显示**：
  - pipeline 结构化事件（stage/progress/meta/lyric）已有 → 保持；新增 provider 级解析状态作为 `message` 事件（`search_metadata` 每源 emit「解析元数据: 咪咕/网易云」，`fetch_lyrics` 每源 emit「获取歌词: 尝试 LRCLIB/网易云/B站字幕」）→ 三端都显示。
  - CLI 额外：config 向导「等待输入 / 已设置 X」、`_ask_index`「等待输入」→ `status.emit`。
  - search_versions「正在搜索 / 命中 N 条（direct X / lyric Y）」→ `status.emit`。
- providers/services 用 `get_logger` 记 DEBUG/INFO/WARNING（HTTP 摘要、源降级、fallback）。

## 技巧

- console handler 加 `addFilter(lambda r: not r.name.startswith("bilimuse.status"))`：emit(WARNING) 由 UI echo，不重复打控制台；内部 `logger.warning`（provider 降级）仍可见 → `logging_setup.py`
- `status.emit` 是同步的（config 向导用 `input()` 阻塞），显示回调也是同步 `typer.echo`；pipeline 的异步 `on_event` 独立保留（三端结构化事件）→ 两通道各司其职
- provider 加 `label` 属性（migu→咪咕、netease→网易云）供显示 → `providers/meta.py`

## API / 库 速查

- `logging.RotatingFileHandler`：`maxBytes=1_000_000, backupCount=3` 滚动 → `logging_setup.py`
- `logging` 命名空间：子 logger 继承根 handler（propagate），一处 setup 全局生效 → `logging_setup.py`

## 踩坑

- **pytest 日志捕获插件干扰**：pytest 往 logger 挂 handler 后，`setup_logging` 的"已有 handler 就跳过"守卫导致不重建到测试目录（文件 0 字节）。→ 改为**总是移除旧 handler 并重建**（幂等且支持运行时改配置）→ `logging_setup.py`。
- **`search_video` 双分支**：已登录走 wbi 分支直接 `return`，末尾 INFO 日志不执行 → 两分支都记「B站搜索 '%s' -> %d 条」→ `bilibili.py`。
- **console WARNING 重复**：emit(WARNING) 若不排除 status，会出现"控制台 + UI echo"双输出 → 加 filter。

## 验证

- `bilimuse search "晴天"` → 日志文件生成含 `INFO bilimuse.bilibili B站搜索 '晴天' -> 2 条` ✅
- `bilimuse config`（管道输入）→ 控制台显示「等待输入: 下载目录...」，日志含「已设置 download_dir = downloads / format / lyric_sources / align / sessdata / proxy」✅
- `bilimuse doctor` → 显示 `日志: .../logs/bilimuse.log（level=INFO）` ✅
- 单测 `tests/test_logging.py`：文件生成/`emit` 双写/级别过滤（DEBUG 进日志不显示、WARNING 两者都）✅（66 passed）
- `python -m ruff check bilimuse tests`：All checks passed ✅

