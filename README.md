# BiliMuse

B 站深度定制的音乐下载器：搜索歌名/歌手/歌词 → 选版本 → 下载纯音频 → 自动打标签 → 自动配歌词 → 自动校准时间轴 → 内嵌封面。

## 安装

需要 Python 3.11+。

**方式一：一键脚本（推荐）**

```bash
# Windows
.\setup.ps1                  # 轻量模式（仅 m4a）
.\setup.ps1 -WithFfmpeg      # 完整模式（支持 mp3/flac）

# Linux / macOS
./setup.sh                   # 轻量模式
./setup.sh --with-ffmpeg     # 完整模式
```

**方式二：手动**

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows；Linux/macOS: source .venv/bin/activate
pip install -e .              # 轻量（m4a）
pip install -e ".[ffmpeg]"    # 完整（mp3/flac，内嵌 imageio-ffmpeg）
```

> ffmpeg 说明：`.[ffmpeg]` 通过 PyPI 拉取 `imageio-ffmpeg`（~60MB 静态 ffmpeg，内含 libmp3lame），装完即用、不依赖系统环境、不经 GitHub。仅下载 m4a 可不装。

### 运行方式（三种任选）

| 方式 | 命令 |
|---|---|
| **一键 TUI** | 双击 `bilimuse-tui.cmd`（Win）/ `./bilimuse-tui`（Unix） |
| **项目目录命令** | cmd: `bilimuse tui`；PowerShell: `.\bilimuse tui`；Unix: `./bilimuse.sh tui` |
| **激活 venv** | `.\.venv\Scripts\Activate.ps1` 后任意目录 `bilimuse` |

首次使用先跑配置向导：双击 `bilimuse-config.cmd` 或 `bilimuse config`（设置下载目录/格式/登录等，免手编 json）。

> 歌词精确校准（可选）：`pip install -e ".[align]"` 装 lyric-align（faster-whisper），歌词时间轴失配时自动强制对齐。语言自动检测（日语歌自动用日语识别），模型默认 `small`（约 460MB），国内推荐从 ModelScope 下载后把 `whisper_model` 配成本地路径：
> ```
> pip install modelscope
> modelscope download --model Systran/faster-whisper-small --local_dir models/faster-whisper-small
> # 然后 config.json 里 "whisper_model": "models/faster-whisper-small"
> ```
> 更准但更慢可用 `medium`/`large-v3-turbo`；混音重伴奏歌可装 `pip install -e ".[separate]"` 并设 `"vocal_separate": true`（Demucs 人声分离，需 torch）。

## 使用

```bash
bilimuse get "窗外的麻雀 在电线杆上多嘴"   # 一键闭环：歌词/歌名搜索→选版本→下载→打标签→配歌词校准
bilimuse get "周杰伦 晴天" --auto          # 自动选第一条（脚本化）
bilimuse get "晴天" --index 2              # 直接选第 2 条
bilimuse tui                               # Textual 交互式界面（需 pip install -e ".[tui]"）
bilimuse web                               # Web 界面（需 pip install -e ".[web]"），默认 http://127.0.0.1:8000
bilimuse model list                        # 模型检测
bilimuse model download small              # 下载模型（ModelScope/HF）
bilimuse search "周杰伦 晴天"     # 搜索 B 站版本
bilimuse info BV1d4411N7zD        # 查看视频详情/分 P
bilimuse download BV1d4411N7zD --format mp3   # 下载（自动打标签 + 配歌词校准，写 .lrc）
bilimuse download BV1d4411N7zD --no-lyric     # 跳过歌词
bilimuse download BV1d4411N7zD --align        # 歌词强制 whisper 校准
bilimuse list-downloads           # 下载历史
bilimuse login                    # 手机扫码登录 B 站（降低风控/提升音质）
bilimuse logout                   # 退出登录
bilimuse doctor --network         # 环境诊断 + 数据源连通性探测
```

> `get` 支持**歌词片段搜索**：输入一句歌词（如"窗外的麻雀 在电线杆上多嘴"），自动经网易云反查真实歌名 → 再去 B 站选版本。

## Web 界面

浏览器操作，适合批量/服务化。使用流程：

**1. 安装 Web 依赖**

```bash
pip install -e ".[web]"        # fastapi / uvicorn / websockets
```

**2. 启动**

```bash
bilimuse web                # 默认 http://127.0.0.1:8000
bilimuse web --port 9000    # 换端口
bilimuse web --host 0.0.0.0 # 局域网其他设备访问
```

（cmd 下：`.\bilimuse web`；Unix：`./bilimuse.sh web`）

**3. 浏览器打开** `http://127.0.0.1:8000`

- **搜索**：输入歌名 / 歌手 / **歌词片段**（如"窗外的麻雀 在电线杆上多嘴"）回车 → 结果表显示来源（`歌词反查`/`直接`）、BV号、时长、播放量、UP主、标题
- **下载**：点击结果行 → 页面顶部实时显示：阶段状态（下载中→反查元数据→获取歌词→whisper 校准）、下载进度条、日志面板（元数据/歌词来源/校准方法/保存路径）
- **顶部信息栏**：Python 版本、登录态、lyric-align/模型状态、已检测模型

**4. HTTP API**（可脚本化）

| 接口 | 说明 |
|---|---|
| `GET /api/search?q=晴天&limit=10` | 两跳搜索（含歌词反查） |
| `GET /api/doctor` | 环境 + 模型解析 + 检测列表 |
| `GET /api/model` | 模型信息（resolve + detect + sizes） |
| `WS /ws/download` | WebSocket：发送 `{"bvid":"BV1...","page":1,"format":"m4a"}` → 推送进度事件（`stage`/`progress`/`meta`/`lyric`/`warning`/`result`/`error`） |

**提示**
- 首次使用先在 `bilimuse config` 向导里登录 B 站（提升音质/风控）并配置 `whisper_model` 为本地模型，Web 端直接生效。
- 下载产物（音频 + `.lrc` 侧车）默认在 `downloads/`（config 的 `download_dir`）。

## 配置

配置文件位于 `%APPDATA%\bilimuse\config.json`（Windows）或 `~/.config/bilimuse/config.json`（Linux/macOS）：

```json
{
  "download_dir": "downloads",
  "format": "m4a",
  "sessdata": "",
  "proxy": "",
  "ffmpeg_path": "",
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

- `sessdata`：B 站登录 cookie（`bilimuse login` 扫码写入），可提升音质、解锁 AI 字幕歌词兜底。
- `proxy`：需要代理访问 B 站时填写。
- `ffmpeg_path`：显式指定系统 ffmpeg，优先于内嵌版本。
- `lyric_sources`：歌词源降级顺序。
- `search_lyric_lookup`：搜索时是否经网易云按歌词正文反查歌名（默认开，歌词片段搜索的关键）。
- `translation_enabled`：外文歌自动配中文译文（网易云 tlyric 双语合并，默认开）。
- `whisper_model`：whisper 模型名（`tiny/base/small/medium/large-v3-turbo`）或本地目录路径（推荐 ModelScope 下载后填路径）。
- `whisper_language`：ASR 语言兜底（自动检测失败时用，默认 `zh`）。
- `vocal_separate`：是否 Demucs 人声分离（需 `.[separate]`，混音重伴奏歌更准）。
- `log_level`：日志级别（`DEBUG/INFO/WARNING/ERROR`，默认 `INFO`；环境变量 `MUSICALBILI_LOG_LEVEL` 可覆盖）。

## 日志与状态显示

- **日志文件**：`<配置目录>/logs/bilimuse.log`（1MB×3 滚动；Win `%APPDATA%\bilimuse\logs`，Linux `~/.config/bilimuse/logs`）。
- **统一状态通道**：CLI/TUI/Web 三端动态显示"系统在做什么"——搜索（含歌词反查）、解析元数据（按源：咪咕/网易云）、获取歌词（按源：LRCLIB/网易云/B站字幕）、下载进度、whisper 校准（步骤级）、配置向导（等待输入/已设置）。同一条状态同时写入日志，方便排查。
- 排查：`bilimuse doctor` 显示日志路径；部署问题看 `setup.log`。

## 便携模式

默认配置文件在系统目录（`%APPDATA%\bilimuse`）。开启**便携模式**后，`config.json`/`downloads.db`/`logs/` 全部移到项目内 `data/`，连同 `downloads/`、`models/`、`.venv/` 都在项目目录里——**整个文件夹拷走即用、即用即下即删即走**，不污染系统环境。

```bash
bilimuse portable on     # 开启：创建 .portable，并把现有配置(含登录态)复制到 data/
bilimuse portable off    # 关闭：删除 .portable（数据保留在 data/）
bilimuse doctor          # 查看当前 模式(便携/标准) + 配置目录
```

- 也可用环境变量 `MUSICALBILI_PORTABLE=1`（一次会话）或安装时 `setup.ps1 -Portable` / `setup.sh --portable`。
- `.portable` 标记文件随目录走：拷到别处仍保持便携；克隆仓库默认标准模式。
- 下载与模型目录 `downloads/`、`models/` 始终在项目内，不随模式变化。

## License

本项目采用 **GPL-3.0-or-later**（见 [LICENSE](LICENSE)）。

许可说明：
- 核心依赖 `mutagen`（打标签）为 **GPL-2.0-or-later**，故本项目需 GPL 兼容；其余依赖（httpx BSD-3 / pydantic / typer / textual / fastapi / lyric-align / faster-whisper 等 MIT）均兼容 GPL-3.0。
- 可选 `[ffmpeg]` extra 内嵌的 ffmpeg（imageio-ffmpeg）含 GPL 组件，若未来打包独立可执行文件分发，需按 GPL 附带源码与许可声明。

## 项目文档

- 需求与调研：[idea.md](idea.md) ｜ 技术方案：[PLAN.md](PLAN.md) ｜ 开发日志：[docs/devlog](docs/devlog/)
