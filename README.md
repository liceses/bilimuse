# MusicalBILI

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
| **一键 TUI** | 双击 `musicalbili-tui.cmd`（Win）/ `./musicalbili-tui`（Unix） |
| **项目目录命令** | cmd: `musicalbili tui`；PowerShell: `.\musicalbili tui`；Unix: `./musicalbili.sh tui` |
| **激活 venv** | `.\.venv\Scripts\Activate.ps1` 后任意目录 `musicalbili` |

首次使用先跑配置向导：双击 `musicalbili-config.cmd` 或 `musicalbili config`（设置下载目录/格式/登录等，免手编 json）。

> 歌词精确校准（可选）：`pip install -e ".[align]"` 装 lyric-align（faster-whisper），歌词时间轴失配时自动强制对齐。语言自动检测（日语歌自动用日语识别），模型默认 `small`（约 460MB），国内推荐从 ModelScope 下载后把 `whisper_model` 配成本地路径：
> ```
> pip install modelscope
> modelscope download --model Systran/faster-whisper-small --local_dir models/faster-whisper-small
> # 然后 config.json 里 "whisper_model": "models/faster-whisper-small"
> ```
> 更准但更慢可用 `medium`/`large-v3-turbo`；混音重伴奏歌可装 `pip install -e ".[separate]"` 并设 `"vocal_separate": true`（Demucs 人声分离，需 torch）。

## 使用

```bash
musicalbili get "窗外的麻雀 在电线杆上多嘴"   # 一键闭环：歌词/歌名搜索→选版本→下载→打标签→配歌词校准
musicalbili get "周杰伦 晴天" --auto          # 自动选第一条（脚本化）
musicalbili get "晴天" --index 2              # 直接选第 2 条
musicalbili tui                               # Textual 交互式界面（需 pip install -e ".[tui]"）
musicalbili web                               # Web 界面（需 pip install -e ".[web]"），默认 http://127.0.0.1:8000
musicalbili model list                        # 模型检测
musicalbili model download small              # 下载模型（ModelScope/HF）
musicalbili search "周杰伦 晴天"     # 搜索 B 站版本
musicalbili info BV1d4411N7zD        # 查看视频详情/分 P
musicalbili download BV1d4411N7zD --format mp3   # 下载（自动打标签 + 配歌词校准，写 .lrc）
musicalbili download BV1d4411N7zD --no-lyric     # 跳过歌词
musicalbili download BV1d4411N7zD --align        # 歌词强制 whisper 校准
musicalbili list-downloads           # 下载历史
musicalbili login                    # 手机扫码登录 B 站（降低风控/提升音质）
musicalbili logout                   # 退出登录
musicalbili doctor --network         # 环境诊断 + 数据源连通性探测
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
musicalbili web                # 默认 http://127.0.0.1:8000
musicalbili web --port 9000    # 换端口
musicalbili web --host 0.0.0.0 # 局域网其他设备访问
```

（cmd 下：`.\musicalbili web`；Unix：`./musicalbili.sh web`）

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
- 首次使用先在 `musicalbili config` 向导里登录 B 站（提升音质/风控）并配置 `whisper_model` 为本地模型，Web 端直接生效。
- 下载产物（音频 + `.lrc` 侧车）默认在 `downloads/`（config 的 `download_dir`）。

## 配置

配置文件位于 `%APPDATA%\musicalbili\config.json`（Windows）或 `~/.config/musicalbili/config.json`（Linux/macOS）：

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
  "hf_mirror": "https://hf-mirror.com"
}
```

- `sessdata`：B 站登录 cookie（`musicalbili login` 扫码写入），可提升音质、解锁 AI 字幕歌词兜底。
- `proxy`：需要代理访问 B 站时填写。
- `ffmpeg_path`：显式指定系统 ffmpeg，优先于内嵌版本。
- `lyric_sources`：歌词源降级顺序。
- `search_lyric_lookup`：搜索时是否经网易云按歌词正文反查歌名（默认开，歌词片段搜索的关键）。
- `translation_enabled`：外文歌自动配中文译文（网易云 tlyric 双语合并，默认开）。
- `whisper_model`：whisper 模型名（`tiny/base/small/medium/large-v3-turbo`）或本地目录路径（推荐 ModelScope 下载后填路径）。
- `whisper_language`：ASR 语言兜底（自动检测失败时用，默认 `zh`）。
- `vocal_separate`：是否 Demucs 人声分离（需 `.[separate]`，混音重伴奏歌更准）。

## 项目文档

- 需求与调研：[idea.md](idea.md) ｜ 技术方案：[PLAN.md](PLAN.md) ｜ 开发日志：[docs/devlog](docs/devlog/)
