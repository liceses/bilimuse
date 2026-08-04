# 一键闭环 pipeline + 搜索（歌词反查）+ Textual TUI 开发日志

- 日期：2026-08-04
- 里程碑：M5
- 关联：PLAN.md M5；[M3 元数据](2026-08-03-metadata-tagger.md)、[M4 歌词校准](2026-08-03-lyric-align.md)

## 目标与验收

- 目标：`bilimuse get "歌名/歌词"` 一键闭环（搜索→选版本→下载→打标签→配歌词校准→入库）；编排抽成服务供 CLI/TUI/Web 复用；Textual 交互式界面
- 验收标准：
  - **歌词片段搜索**：输入一句歌词 → 反查真实歌名 → B站 返回正确版本 ✅
  - `get` 交互选序号 + `--index`/`--auto` 脚本化 ✅
  - `download` 命令改走同一 pipeline ✅
  - `tui` Textual 界面：搜索→结果表→选中下载 ✅

## 方案与思路（含否决方案）

### 歌词片段 → 歌名的第一跳（关键调研）

- **否决**：LRCLIB `/api/search`（实测**不匹配歌词正文**，片段 0 条，歌名+歌手 20 条）。
- **否决**：B站 直接搜歌词片段——只对"标题即歌词"的热门翻唱有效，且**拿不到真歌名**（后续元数据/歌词反查会失败，之前翻唱匹配失败就是这原因）。
- **选定**：网易云 weapi 搜索 `s` 参数**实测支持歌词正文匹配**——"窗外的麻雀…"→七里香、"初めてのルーブルは"→One Last Kiss。返回歌名正确（歌手是翻唱者，真实原唱靠 M3 按歌名反查）。
- 两路合并：B站 直接搜 query + 网易云反查歌名(前3)各搜一次 B站，去重、按播放量排序、标注来源（direct/lyric）。

### pipeline 事件化

- 编排从 cli 抽到 `services/pipeline.py`，`on_event` 回调推结构化事件（info/progress/message/meta/lyric/warning），CLI `_echo_events` 打印、TUI 更新面板、M6 Web 可复用。

## 技巧

- 网易云搜索 `s` 参数即歌词正文搜索（无额外接口），返回歌名正确但歌手是翻唱者 → 只用其歌名 → `services/search.py:_lyric_to_titles`
- 去重逻辑：`title.lower() in query.lower()` 判断"歌名已在 query 中"（歌名查询时跳过反查省请求）→ `search.py:44`
- Textual 8 的 `Input.action_submit()` 是**协程需 await**（headless 测试踩坑）→ `tui.py:on_input_submitted` 直接 `run_worker(do_search())`

## API / 库 速查

- 网易云 `weapi/search/get/web` `s=<歌词片段>`：歌词正文搜索（免费）→ `search.py:_lyric_to_titles`
- `textual.App`：`compose()` 布局、`run_worker()` 跑异步、`query_one()` 取控件、`DataTable.add_columns/add_row/cursor_type` → `tui.py`

## 踩坑

- **LRCLIB 不搜歌词正文**：`/api/search?q=` 只匹配标题/艺人/专辑 → 歌词反查改走网易云。
- **B站直接搜歌词拿不到歌名**：结果标题是歌词片段非歌名 → 必须两跳反查。
- **Textual `action_submit` 未 await**：`inp.action_submit()` 直接调用返回未 await 协程 → 搜索不触发；需 `await`。
- **`run_worker` 在 `run_test` headless 可用**：需 `pilot.pause()` 驱动事件循环，轮询 row_count 等结果。

## 验证

- `search_versions('窗外的麻雀 在电线杆上多嘴')`：10 条，前 5 为 lyric 反查（真七里香版本，播放 2600万），含 direct 琴谱 ✅
- `bilimuse get "窗外的麻雀 在电线杆上多嘴" --auto`：歌词反查→选中→下载→migu「周杰伦 - 七里香」→LRCLIB 歌词→.lrc ✅
- TUI headless：挂载 8 控件；输入"晴天 周杰伦"→ DataTable 20 行（首行晴天MV）✅
- 单测：`search_versions` 两路合并/去重/关闭开关；`download_song_pipeline` 事件流/`--no-tag --no-lyric` ✅（49 passed）
- `python -m ruff check bilimuse tests`：All checks passed ✅

## 运行便利化：命令 shim + 一键脚本 + 配置向导（同日补充）

### 问题

- `bilimuse.exe` 已生成，但 venv 未激活时 `.venv\Scripts` 不在 PATH → 终端输入 `bilimuse` 找不到命令。
- 决策：**不改用户 PATH**，用项目目录 shim + 一键脚本解决。

### 实现

1. **shim**：`bilimuse.cmd`（Win）/ `bilimuse.sh`（Unix）→ 调 `.venv` 内 python `-m bilimuse`。
   - cmd 项目目录直接 `bilimuse tui`；PS 用 `.\bilimuse`；激活 venv 后任意目录 `bilimuse`。
   - **踩坑**：Unix 下 `bilimuse` 与包目录 `bilimuse/` 同名冲突 → Unix 通用 shim 改名 `bilimuse.sh`。
   - **踩坑**：`.cmd` 文件含中文注释在 cmd.exe(GBK) 下解析崩（`rem` 被破坏）→ `.cmd` 只写 ASCII。
2. **一键脚本**：`bilimuse-tui.cmd`/`bilimuse-tui`（双击进 TUI）、`bilimuse-config.cmd`/`bilimuse-config`（双击配置向导）。
3. **`bilimuse config` 交互向导**：下载目录/格式/歌词源/校准开关/whisper模型/扫码登录/代理 七项，免手编 json，保存+摘要。
4. **setup.ps1/sh**：安装后打印运行方式；README 部署节三表。

### 踩坑

- **`Config.save` 不能序列化 Path**：`json.dumps(vars(cfg))` 遇 `download_dir`(WindowsPath) 抛 `TypeError: Object of type WindowsPath is not JSON serializable`——`login`/`logout` 一直有这隐患（未走全）。修复：save 时 `str(download_dir)` → `config.py:save`。
- **Windows Path 规范化**：`Path("D:/Music")` → `str()` 为 `D:\Music`，断言用 Path 比较。

### 验证

- `.\bilimuse.cmd --help` / `.\bilimuse.cmd tui --help`：shim 生效 ✅
- `bilimuse config` 管道输入 7 项 → 保存正确（download_dir 字符串化）✅
- 单测：config 保存/加载往返、向导（mock input）✅（51 passed）

## 踩坑：TUI 选中回车无反应（RowKey.value 为 None）

- **现象**：TUI 能进、能高亮行，但回车无反应。
- **根因**：`DataTable.add_row()` 不带显式 key 时自动生成 `RowKey` 对象，其 `.value` 是 **None**；`on_data_table_row_selected` 里 `int(event.row_key.value)` 抛 TypeError → handler 静默失败。
- **修复**：改用 `DataTable.get_row_index(event.row_key)` 取行索引 → `bilimuse/tui.py:on_data_table_row_selected`。
- **验证**：headless `pilot` 下 `down+enter` 选中第 2 行 → pipeline 被调用（BV2）；新增 `tests/test_tui.py` 回归（`importorskip("textual")`）✅（53 passed）

## Bug 修复（Beautiful World 标签 + whisper 卡住 + TUI 进度细化）

### Bug 1：Beautiful World 标签打错（pick_best 增强 + 合并候选池）

- **现象**：EVA Beautiful World 被标成 "Robin Thicke - A Beautiful World"。
- **根因**：① query "A Beautiful World" 时 migu 精确命中 Robin Thicke（同名 1.0 分）；② **migu 命中即返回，netease（有正确 宇多田 316s）根本没被咨询**；③ 无时长约束，同名异歌手/版本无法区分。
- **修复**：
  1. `search_metadata`/`auto_tag` **合并所有源候选统一 `pick_best`**（不再首源命中即返回），tie 仍 migu 优先 → `services/tagger.py`。
  2. `pick_best(..., duration=视频时长)`：netease 候选 `|dur−video|≤8s +0.25 / ≤30s +0.05 / 否则 −0.2`。
  3. **版本后缀惩罚**（Remastered/Live/Karaoke/Da Capo/翻唱/Cover −0.15）。
  - pipeline 传入视频时长；`search_metadata` 每源只搜一次（结果缓存）。
- **验证**：`Beautiful World EVA`/`宇多田ヒカル - Beautiful World`/4 个真实 EVA 视频标题 → 全部正确标 **宇多田ヒカル - Beautiful World**（时长命中）。
- **边界**：若视频标题字面就是 "A Beautiful World"（宇多田不在任何源结果池），无法凭空猜是 EVA 歌——信息不足，接受。

### Bug 2：whisper 卡住（模型引导 + 子进程清理）

- **根因**：无配置 → `whisper_model="small"` → 从 HF(hf-mirror <15KB/s) 下载模型 → 卡住；中断后 asyncio 子进程传输未清理 → `BaseSubprocessTransport.__del__` 告警。
- **修复**：
  1. `calibrate_align` 跑前 `on_status` 提示"正在 whisper 校准（首次需下载模型或配置本地路径，可能较久）"。
  2. `config` 向导检测到 `models/faster-whisper-small` 存在 → 默认填本地路径。
  3. `probe_duration`/`calibrate_align`/`convert_audio`/`fetch_cover_bytes` 子进程 **try/finally + proc.kill() + await wait()**（防中断泄漏告警）。

### TUI 进度细化

- 新增 `ProgressBar`（下载进度）+ 状态行（当前阶段/歌曲/校准提示）。
- pipeline 发 `stage`（download/tag/lyric/done）+ `align_start` 类 message；`_echo_events` 兼容。
- headless 验证：进度条到 100、状态"完成"。

### 验证

- `pick_best` 时长/后缀单测 + `search_metadata` 合并池 ✅（55 passed）
- 真实 EVA 标题 4 例全标 宇多田 ✅
- TUI headless：ProgressBar 100 + status 完成 ✅

## 模型信息管理（检测 / 展示 / 进度 / 下载）

### 能力

1. **检测**：`detect_models()` 扫 `models/`（本地）+ HF 缓存 `~/.cache/huggingface/hub/models--Systran--faster-whisper-*`；`resolve_model()` 解析 `whisper_model` → 本地/缓存/缺失。
2. **CLI `bilimuse model`**：`list`（检测+配置解析+可下载名单+依赖状态）、`download <size> [--source modelscope|hf] [--no-set]`、`set <size|path>`。
3. **进度（步骤级）**：`calibrate_align` 去 `-q`，**流式读 stderr** → 每行 emit 状态（"转写中…/分段 N/匹配阈值/对齐 X/Y 行/wrote out.json"）；跑前 emit **"使用模型: <resolved>（本地/HF缓存/待下载）"**。
4. **doctor**：显示 lyric-align/faster-whisper 安装状态 + resolved 模型 + 检测列表。
5. **下载**：ModelScope（默认，国内快）`www.modelscope.cn/models/Systran/faster-whisper-<size>/resolve/master/`，文件 404 跳过（config/model.bin/tokenizer/vocabulary）；`--source hf` 走 HF_ENDPOINT 镜像。

### 踩坑

- lyric-align `-q` 抑制所有进度日志 → 流式需去掉 `-q`；失败详情改为流式尾部（`tail_holder`）。
- `_stream_stderr` 用 `asyncio.create_task` 逐行读 `proc.stderr`，主任务 `proc.wait()`；退出时 cancel 任务 + kill（防泄漏告警，沿用之前修复）。

### 验证

- `model list`：显示本地 small(486MB) + HF缓存 small + 配置解析"small→HF 缓存" ✅
- `model download base`：ModelScope 4 文件下载到 `models/faster-whisper-base`（model.bin 145MB）✅
- `model set models/faster-whisper-base`：写配置 ✅
- 校准流式：`[状态] 使用模型… / line 16-32 sim… / only 4/32 lines matched… / wrote out.json` ✅（base 模型弱匹配 4/32，正体现进度可见性）
- 单测：`resolve_model` 本地/缺失/未配置 ✅（58 passed）

### 待办（后续）

- [ ] whisper 识别**百分比进度**（绕过 lyric-align CLI，直接调 faster-whisper `progress_callback` + lyric_align.align 库，耦合更深）
- [ ] TUI **完整模型管理面板**（快捷键调出：list/download/set）
