# 一键闭环 pipeline + 搜索（歌词反查）+ Textual TUI 开发日志

- 日期：2026-08-04
- 里程碑：M5
- 关联：PLAN.md M5；[M3 元数据](2026-08-03-metadata-tagger.md)、[M4 歌词校准](2026-08-03-lyric-align.md)

## 目标与验收

- 目标：`musicalbili get "歌名/歌词"` 一键闭环（搜索→选版本→下载→打标签→配歌词校准→入库）；编排抽成服务供 CLI/TUI/Web 复用；Textual 交互式界面
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
- `musicalbili get "窗外的麻雀 在电线杆上多嘴" --auto`：歌词反查→选中→下载→migu「周杰伦 - 七里香」→LRCLIB 歌词→.lrc ✅
- TUI headless：挂载 8 控件；输入"晴天 周杰伦"→ DataTable 20 行（首行晴天MV）✅
- 单测：`search_versions` 两路合并/去重/关闭开关；`download_song_pipeline` 事件流/`--no-tag --no-lyric` ✅（49 passed）
- `python -m ruff check musicalbili tests`：All checks passed ✅

## 运行便利化：命令 shim + 一键脚本 + 配置向导（同日补充）

### 问题

- `musicalbili.exe` 已生成，但 venv 未激活时 `.venv\Scripts` 不在 PATH → 终端输入 `musicalbili` 找不到命令。
- 决策：**不改用户 PATH**，用项目目录 shim + 一键脚本解决。

### 实现

1. **shim**：`musicalbili.cmd`（Win）/ `musicalbili.sh`（Unix）→ 调 `.venv` 内 python `-m musicalbili`。
   - cmd 项目目录直接 `musicalbili tui`；PS 用 `.\musicalbili`；激活 venv 后任意目录 `musicalbili`。
   - **踩坑**：Unix 下 `musicalbili` 与包目录 `musicalbili/` 同名冲突 → Unix 通用 shim 改名 `musicalbili.sh`。
   - **踩坑**：`.cmd` 文件含中文注释在 cmd.exe(GBK) 下解析崩（`rem` 被破坏）→ `.cmd` 只写 ASCII。
2. **一键脚本**：`musicalbili-tui.cmd`/`musicalbili-tui`（双击进 TUI）、`musicalbili-config.cmd`/`musicalbili-config`（双击配置向导）。
3. **`musicalbili config` 交互向导**：下载目录/格式/歌词源/校准开关/whisper模型/扫码登录/代理 七项，免手编 json，保存+摘要。
4. **setup.ps1/sh**：安装后打印运行方式；README 部署节三表。

### 踩坑

- **`Config.save` 不能序列化 Path**：`json.dumps(vars(cfg))` 遇 `download_dir`(WindowsPath) 抛 `TypeError: Object of type WindowsPath is not JSON serializable`——`login`/`logout` 一直有这隐患（未走全）。修复：save 时 `str(download_dir)` → `config.py:save`。
- **Windows Path 规范化**：`Path("D:/Music")` → `str()` 为 `D:\Music`，断言用 Path 比较。

### 验证

- `.\musicalbili.cmd --help` / `.\musicalbili.cmd tui --help`：shim 生效 ✅
- `musicalbili config` 管道输入 7 项 → 保存正确（download_dir 字符串化）✅
- 单测：config 保存/加载往返、向导（mock input）✅（51 passed）
