# BiliMuse

B 站深度定制的音乐下载器：**歌词片段反查** + **whisper 时间轴自动校准**。

搜索歌名/歌手/**歌词** → 选版本 → 下载纯音频 → 自动打标签 → 自动配歌词 → 自动校准时间轴 → 内嵌封面，一键闭环。

## 特性

- **两跳搜索**：输入一句歌词（如「窗外的麻雀 在电线杆上多嘴」）→ 网易云反查真实歌名 → B 站选版本
- **一键闭环**：`bilimuse get` 搜索→选版本→下载→打标签→配歌词→校准→入库，全程结构化事件
- **多源元数据**：咪咕优先 + 网易云兜底，统一打分选最优（歌名/歌手/时长/版本惩罚）；mutagen 打标签，webp 封面自动转 jpeg 内嵌
- **多源歌词**：LRCLIB → 网易云 → B 站 AI 字幕降级；外文歌自动配中文译文（网易云双语逐行合并）
- **whisper 时间轴校准**：语言自动检测（日语歌自动用日语识别）、锚点线性拟合治前留白、置信度过低自动回退不瞎改
- **三端界面**：CLI / Textual TUI / Web（FastAPI + WebSocket 实时进度）
- **便携模式（安装默认）**：config/db/日志全在项目 `data/`，整个文件夹拷走即用、不污染系统
- **模型管理**：`bilimuse model` 检测/下载/切换，ModelScope 国内高速下载
- **真实网络 E2E 测试集**：35 条用例 + 5 首人工标注基准

## 安装

需要 Python 3.11+。

**方式一：统一入口（推荐）**

双击 `bilimuse-start.cmd`（Windows）/ 运行 `./bilimuse-start`（Unix）——一个入口搞定「安装 → 配置 → 使用」：首次运行自动建 venv 装全量依赖、自动开启便携模式、自动打开配置向导，之后从菜单启动 TUI / Web / 命令行。

也可命令行安装：

```bash
# Windows
.\setup.ps1                  # 全量安装，默认便携模式（推荐）
.\setup.ps1 -Standard        # 标准模式（config/logs/db 放 %APPDATA%\bilimuse）
.\setup.ps1 -Lite            # 轻量模式（仅 m4a）
.\setup.ps1 -Mirror ""       # 使用官方 PyPI（默认清华镜像）

# Linux / macOS
./setup.sh                   # 全量安装，默认便携模式（推荐）
./setup.sh --standard        # 标准模式（config/logs/db 放 ~/.config/bilimuse）
./setup.sh --lite            # 轻量模式（仅 m4a）
MIRROR= ./setup.sh           # 使用官方 PyPI（默认清华镜像）
```

**方式二：手动**

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows；Linux/macOS: source .venv/bin/activate
pip install -e .              # 轻量（m4a）
pip install -e ".[ffmpeg,align,tui,web,dev]"    # 全量（mp3/flac + TUI/Web + 歌词校准）
```

> ffmpeg 说明：`.[ffmpeg]` 通过 PyPI 拉取 `imageio-ffmpeg`（~60MB 静态 ffmpeg，内含 libmp3lame），装完即用、不依赖系统环境、不经 GitHub。仅下载 m4a 可不装。

### 运行方式（四种任选）

| 方式 | 命令 |
|---|---|
| **统一入口（推荐）** | 双击 `bilimuse-start.cmd`（Win）/ `./bilimuse-start`（Unix）：安装→配置→TUI/Web 菜单；也支持 `bilimuse-start config\|tui\|web` 直达 |
| **一键 TUI** | 双击 `bilimuse-tui.cmd`（Win）/ `./bilimuse-tui`（Unix） |
| **项目目录命令** | cmd: `bilimuse tui`；PowerShell: `.\bilimuse tui`；Unix: `./bilimuse.sh tui` |
| **激活 venv** | `.\.venv\Scripts\Activate.ps1` 后任意目录 `bilimuse` |

## 快速开始

**1. 配置**（首次必做，向导免手编 json）：

```bash
bilimuse config          # 或双击 bilimuse-config.cmd / 统一入口首次运行自动打开
```

向导设置：下载目录 / 格式 / 歌词源 / 校准开关 / whisper 模型（检测到本地模型自动填路径）/ 扫码登录 B 站 / 代理。建议勾选扫码登录（降风控、提音质）。

**2. 一键下载**：

```bash
bilimuse get "窗外的麻雀 在电线杆上多嘴"    # 歌词片段 → 反查「七里香」→ B 站选版本 → 下载+打标签+配歌词校准
bilimuse get "周杰伦 晴天"                  # 歌名直搜，交互选版本
bilimuse get "周杰伦 晴天" --auto           # 自动选第一条（脚本化）
bilimuse get "晴天" --index 2               # 直接选第 2 条
```

**3. 找到产物**：`downloads/` 下 `<歌手> - <歌名>.m4a/.mp3` + 同名 `.lrc` 歌词侧车。

## 命令行速查

| 命令 | 说明 |
|---|---|
| `bilimuse get <歌名/歌手/歌词> [--index N\|--auto] [--format m4a\|mp3\|flac] [--no-tag] [--no-lyric] [--align]` | 一键闭环（推荐入口） |
| `bilimuse search <关键词> [--limit N]` | 搜索 B 站版本 |
| `bilimuse info <BV号>` | 查看视频详情 / 分 P |
| `bilimuse download <BV号> [--page N] [--format m4a\|mp3\|flac] [--no-tag] [--no-lyric] [--align]` | 下载单曲（自动打标签 + 配歌词校准） |
| `bilimuse tag <音频文件> [-q 关键词]` | 按网易云反查为已有音频打标签 |
| `bilimuse list-downloads` | 下载历史 |
| `bilimuse login` / `bilimuse logout` | B 站扫码登录 / 退出（降风控、提音质） |
| `bilimuse config` | 交互式配置向导 |
| `bilimuse model list` | 检测本地/HF 缓存模型 + 配置解析 |
| `bilimuse model download small [--source modelscope\|hf] [--no-set]` | 下载 whisper 模型 |
| `bilimuse model set small\|<本地路径>` | 设置 whisper_model |
| `bilimuse portable on\|off` | 便携模式开关（on 时迁移现有配置） |
| `bilimuse doctor [--network]` | 环境诊断 + 数据源连通性探测 |
| `bilimuse tui` | Textual 交互式界面 |
| `bilimuse web [--host 0.0.0.0] [--port 9000]` | Web 界面 |

> `get`/`search` 支持**歌词片段搜索**：输入一句歌词，自动经网易云反查真实歌名，再去 B 站选版本。

## 歌词时间轴校准（差异化能力）

下载后自动配歌词并校准时间轴：

- **多源歌词降级**：LRCLIB → 网易云 → B 站 AI 字幕（需登录兜底）；外文歌自动反查网易云双语（原句 + 中文译文逐行交替）。
- **两级校准**：
  1. **快速校准**：末行时间与音频时长吻合（≤5s）→ 视为已同步直接保存；
  2. **强制对齐**：失配时自动跑 lyric-align（whisper 转写 + 字符级模糊锚定）——翻唱/视频变速等原词能对上但时间轴不对的场景是主战场。
- **语言自动检测**：假名→日语、谚文→韩语、汉字→中文……日语歌自动用日语识别（硬编码 zh 会让匹配率从 96% 掉到 32%）。
- **智能回退**：whisper 对齐置信度 <50% 时不盲目缩放，回退原歌词并警告；锚点 ≥3 用最小二乘整体变换（`align_offset`，治官方 MV 前留白），<3 保留原词。
- **进度可见**：校准流式输出步骤（转写中/分段/匹配阈值/对齐行数/wrote out.json）。

### whisper 模型管理

`whisper_model` 支持模型名或本地目录路径。国内推荐 ModelScope 下载后填本地路径：

```bash
bilimuse model list                        # 检测 models/ + HF 缓存
bilimuse model download small              # ModelScope 下载到 models/faster-whisper-small（默认写入配置）
bilimuse model download large-v3-turbo --source hf   # 或走 HF 镜像
bilimuse model set models/faster-whisper-small       # 手动切换
```

- 模型档位：`tiny/base/small/medium/large-v3-turbo`（small 约 460MB，够用；更大更准更慢）。
- 更准但更慢可用 `medium`/`large-v3-turbo`；混音重伴奏歌可装 `pip install -e ".[separate]"` 并设 `"vocal_separate": true`（Demucs 人声分离，需 torch）。

## Web 界面

浏览器操作，适合批量/服务化。

**1. 安装 Web 依赖**：

```bash
pip install -e ".[web]"        # fastapi / uvicorn / websockets
```

**2. 启动**：

```bash
bilimuse web                # 默认 http://127.0.0.1:8000
bilimuse web --port 9000    # 换端口
bilimuse web --host 0.0.0.0 # 局域网其他设备访问
```

（cmd 下：`.\bilimuse web`；Unix：`./bilimuse.sh web`）

**3. 浏览器打开** `http://127.0.0.1:8000`

- **搜索**：输入歌名 / 歌手 / **歌词片段**（如「窗外的麻雀 在电线杆上多嘴」）回车 → 结果表显示来源（`歌词反查`/`直接`）、BV 号、时长、播放量、UP 主、标题
- **下载**：点击结果行 → 页面顶部实时显示：阶段状态（下载中→反查元数据→获取歌词→whisper 校准）、下载进度条、日志面板（元数据/歌词来源/校准方法/保存路径）
- **顶部信息栏**：Python 版本、登录态、lyric-align/模型状态、已检测模型

**4. HTTP API**（可脚本化）

| 接口 | 说明 |
|---|---|
| `GET /api/search?q=晴天&limit=10` | 两跳搜索（含歌词反查） |
| `GET /api/doctor` | 环境 + 模型解析 + 检测列表 |
| `GET /api/model` | 模型信息（resolve + detect + sizes） |
| `WS /ws/download` | WebSocket：发送 `{"bvid":"BV1...","page":1,"format":"m4a"}` → 推送进度事件（`stage`/`progress`/`meta`/`lyric`/`warning`/`result`/`error`） |

**提示**：首次使用先 `bilimuse config` 向导里登录 B 站并配置本地 `whisper_model`，Web 端直接生效；下载产物默认在 `downloads/`。

## TUI 界面

Textual 交互式终端界面（`pip install -e ".[tui]"`）：

```bash
bilimuse tui
```

输入歌名/歌词搜索 → 结果表选中回车下载 → 进度条 + 阶段状态实时显示。

## 配置

配置文件位于 `data/config.json`（便携模式，默认）或 `%APPDATA%\bilimuse\config.json`（Windows）/ `~/.config/bilimuse/config.json`（Linux/macOS）：

```json
{
  "download_dir": "downloads",
  "format": "m4a",
  "sessdata": "",
  "buvid3": "",
  "proxy": "",
  "ffmpeg_path": "",
  "ua": "Mozilla/5.0 ...",
  "filename_template": "{artist} - {title}.{ext}",
  "lyric_sources": ["lrclib", "netease", "bilibili"],
  "search_lyric_lookup": true,
  "translation_enabled": true,
  "align_enabled": true,
  "whisper_model": "small",
  "whisper_language": "zh",
  "vocal_separate": false,
  "log_level": "INFO",
  "hf_mirror": "https://hf-mirror.com"
}
```

| 字段 | 说明 |
|---|---|
| `download_dir` | 下载目录 |
| `format` | 输出格式 `m4a`（直拷，免 ffmpeg）/ `mp3` / `flac`（需 ffmpeg；flac 仅当源为 VIP 无损流） |
| `sessdata` | B 站登录 cookie（`bilimuse login` 扫码写入），提升音质、降风控、解锁 AI 字幕歌词兜底 |
| `buvid3` | B 站匿名设备标识（自动维护） |
| `proxy` | 需要代理访问 B 站时填写 |
| `ffmpeg_path` | 显式指定系统 ffmpeg，优先于内嵌版本 |
| `filename_template` | 文件名模板，默认 `{artist} - {title}.{ext}` |
| `lyric_sources` | 歌词源降级顺序 |
| `search_lyric_lookup` | 搜索时是否经网易云按歌词正文反查歌名（默认开，歌词片段搜索的关键） |
| `translation_enabled` | 外文歌自动配中文译文（网易云 tlyric 双语合并，默认开） |
| `align_enabled` | 歌词时间轴校准（默认开；关则只做快速校准） |
| `whisper_model` | 模型名或本地目录路径（ModelScope 下载后填路径） |
| `whisper_language` | ASR 语言兜底（自动检测失败时用，默认 `zh`） |
| `vocal_separate` | 是否 Demucs 人声分离（需 `.[separate]`，混音重伴奏歌更准） |
| `log_level` | 日志级别 `DEBUG/INFO/WARNING/ERROR`（默认 `INFO`） |
| `hf_mirror` | HuggingFace 镜像（默认 `hf-mirror.com`） |

环境变量：`MUSICALBILI_CONFIG_DIR`（指定配置目录，优先级最高）、`MUSICALBILI_PORTABLE=1`（一次会话便携）、`MUSICALBILI_LOG_LEVEL`（覆盖日志级别）。

## 便携模式

**安装默认开启**（setup / 统一入口自动创建 `.portable`）：`config.json`/`downloads.db`/`logs/` 全部落在项目内 `data/`，连同 `downloads/`、`models/`、`.venv/` 都在项目目录里——**整个文件夹拷走即用、即用即下即删即走**，不污染系统环境。

```bash
bilimuse portable on     # 手动开启：创建 .portable，并把现有配置(含登录态)复制到 data/
bilimuse portable off    # 关闭：删除 .portable（数据保留在 data/）
bilimuse doctor          # 查看当前 模式(便携/标准) + 配置目录
```

- 不想要便携：安装时用 `setup.ps1 -Standard` / `setup.sh --standard`；或装后 `bilimuse portable off`。
- 也可用环境变量 `MUSICALBILI_PORTABLE=1`（一次会话）触发。
- `.portable` 标记文件随目录走：拷到别处仍保持便携。

## 日志与状态显示

- **日志文件**：`<配置目录>/logs/bilimuse.log`（1MB×3 滚动；便携 `data/logs`，标准 `%APPDATA%\bilimuse\logs` 或 `~/.config/bilimuse/logs`）。
- **统一状态通道**：CLI/TUI/Web 三端动态显示「系统在做什么」——搜索（含歌词反查）、解析元数据（按源：咪咕/网易云）、获取歌词（按源：LRCLIB/网易云/B 站字幕）、下载进度、whisper 校准（步骤级）、配置向导（等待输入/已设置）。同一条状态同时写入日志，方便排查。
- 排查：`bilimuse doctor` 显示日志路径；部署问题看 `setup.log`。

## 测试

```bash
python -m pytest tests -q            # 单元/集成（约 70 例）
python -m ruff check bilimuse tests  # Lint
```

**真实网络 E2E 集**（`tests/e2e/`，35 条用例，YAML 驱动，机器校验 + 人工评审双轨）：

```bash
python tests/e2e/run_testset.py                  # 全套（真实下载链路）
python tests/e2e/run_testset.py --only C01,C05   # 指定用例
python tests/e2e/run_testset.py --no-align       # 关 whisper 校准（快速冒烟）
python tests/e2e/run_testset.py --config-dir <dir>   # 隔离配置目录（含 sessdata/模型，避免污染真实配置）
python tests/e2e/align_bench.py                  # 校准基准：whisper 对齐 vs gold/ 人工标注，算中位误差
pytest -m e2e                                    # 或以 pytest 运行（需真实网络）
```

- 用例矩阵覆盖：中文经典 / 歌词片段反查 / 日英粤韩 / 格式（m4a/mp3/flac）/ 边界异常 / 校准专项 / Web 三端。
- 校准判定：中位误差 ≤1.5s 优、≤3.0s 通过、>3.0s 失败。详见 [tests/e2e/README.md](tests/e2e/README.md)。

## 项目结构

```
bilimuse/
├─ cli.py            # typer CLI 入口 + 配置向导 + model/portable 子命令
├─ config.py         # 配置加载/保存；便携模式单一枢纽 default_config_dir()
├─ db.py             # SQLite 下载历史（bvid+cid 去重）
├─ logging_setup.py  # 文件滚动日志 + console WARNING（filter 排除状态通道）
├─ status.py         # 统一状态通道 emit（日志 + UI 双写）
├─ models.py         # SongMeta / Lyric 数据模型
├─ providers/        # bilibili.py（Wbi 签名/搜索双端点/playurl/AI 字幕）、meta.py（咪咕→网易云）
├─ services/         # search.py（两跳）pipeline.py（事件化闭环）download.py tagger.py lyric.py aligner.py auth.py
├─ tui.py            # Textual 交互式界面
├─ web.py            # FastAPI + WebSocket（复用 pipeline 事件）
└─ web/static/       # 原生单页前端（零构建）

tests/               # 单元/集成测试
tests/e2e/           # 真实网络 E2E 集（cases.yaml + run_testset.py + align_bench.py + gold/）
```

## License

本项目采用 **GPL-3.0-or-later**（见 [LICENSE](LICENSE)）。

许可说明：
- 核心依赖 `mutagen`（打标签）为 **GPL-2.0-or-later**，故本项目需 GPL 兼容；其余依赖（httpx BSD-3 / pydantic / typer / textual / fastapi / lyric-align / faster-whisper 等 MIT）均兼容 GPL-3.0。
- 可选 `[ffmpeg]` extra 内嵌的 ffmpeg（imageio-ffmpeg）含 GPL 组件，若未来打包独立可执行文件分发，需按 GPL 附带源码与许可声明。

## 项目文档

- 需求与调研：[idea.md](idea.md) ｜ 技术方案：[PLAN.md](PLAN.md) ｜ 开发日志：[docs/devlog](docs/devlog/) ｜ E2E 测试集：[tests/e2e/README.md](tests/e2e/README.md)
