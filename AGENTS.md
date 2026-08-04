# AGENTS.md

BiliMuse（包名 `bilimuse`）— Bilibili 音乐下载器。差异化能力：**歌词正文反查** + **whisper 歌词时间轴自动校准**。许可证 GPL-3.0（依赖 mutagen GPL-2.0-or-later，需 GPL 兼容）。

## 常用命令

- 运行：`bilimuse get <歌名/歌词> --auto` / `bilimuse tui` / `bilimuse web` / `bilimuse config` / `bilimuse model list|download|set` / `bilimuse portable on|off` / `bilimuse doctor`
- 测试：`python -m pytest tests -q`（70 单元，e2e 默认排除）；E2E：`python tests/e2e/run_testset.py --config-dir tests/e2e/.runconfig`（34 用例，真实网络）；校准基准：`python tests/e2e/align_bench.py`；`pytest tests/e2e -m e2e`（Web 端）
- Lint：`python -m ruff check bilimuse tests`
- Windows 项目目录直接 `.\bilimuse.cmd <cmd>`；Unix `./bilimuse.sh`

## 架构要点

- **pipeline 事件化**：`services/pipeline.py` 一键闭环（下载→打标签→配歌词→校准→入库），`on_event` 推送结构化事件（info/stage/progress/message/meta/lyric/warning），CLI `_echo_events` / TUI `_log_event` / Web WS 三端复用。
- **统一状态通道**：`status.py` `emit(level,text)` 双写（日志 + UI 显示）；`logging_setup.py` 文件滚动(1MB×3)+console WARNING（filter 排除 status）。
- **providers 多源**：`providers/bilibili.py`（Wbi 签名、搜索双端点、playurl、AI 字幕）、`providers/meta.py`（咪咕优先→网易云兜底，weapi AES+RSA，webp 封面 ffmpeg 转 jpeg）。
- **搜索两跳**：`services/search.py` — B站直接搜 + 网易云 weapi 按歌词正文反查歌名（`s` 参数）→ B站搜。`config.search_lyric_lookup` 开关。
- **歌词校准**：`services/aligner.py` — 语言自动检测（假名→ja 等）、快速校准（synced）、lyric-align 强制对齐（高匹配 interpolate / 低匹配锚点线性拟合 align_offset）、`_robust_fit` 防离群。模型本地 `models/` 或 HF 缓存。
- **打标签**：`services/tagger.py` — `pick_best`（歌名相似+歌手+时长+后缀惩罚）、合并候选池、`pair_translation`+`reattach_translation`（译文校准前后配对）。
- **便携模式**：`config.py` `default_config_dir()` 单一枢纽；`.portable` 标记/env → 数据落项目 `data/`。
- 三端：`tui.py`（Textual，可选 [tui]）、`web.py`（FastAPI+WebSocket，可选 [web]）。

## 约定

- **开发留痕**：每个功能边写边记 `docs/devlog/`（模板 TEMPLATE.md，含 目标/方案/技巧/API速查/踩坑/验证，带 file:line）。完成后更新 `docs/devlog/README.md` 索引 + 技术沉淀速查表。
- 需求/方案见 `idea.md` / `PLAN.md`。
- 敏感数据（SESSDATA/cookie/代理）不落日志不提交；`downloads/`、`models/`、`data/`、`.venv/` gitignore。
- 提交前跑 pytest + ruff；分阶段 commit（一个功能一个 commit）。

## 待办（来自 devlog）

- [ ] whisper 识别百分比进度（绕过 lyric-align CLI，直接调 faster-whisper `progress_callback` + lyric_align.align 库）
- [ ] TUI 完整模型管理面板（快捷键调出 list/download/set）
- [ ] Web 批量下载/歌单（WebSocket 多任务）
- [ ] Web `--config` 指定配置（当前用默认配置目录）
