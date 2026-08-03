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

## 使用

```bash
musicalbili search "周杰伦 晴天"     # 搜索 B 站版本
musicalbili info BV1d4411N7zD        # 查看视频详情/分 P
musicalbili download BV1d4411N7zD --format mp3   # 下载（m4a/mp3/flac）
musicalbili list-downloads           # 下载历史
musicalbili doctor                   # 环境诊断
```

## 配置

配置文件位于 `%APPDATA%\musicalbili\config.json`（Windows）或 `~/.config/musicalbili/config.json`（Linux/macOS）：

```json
{
  "download_dir": "downloads",
  "format": "m4a",
  "sessdata": "",
  "proxy": "",
  "ffmpeg_path": ""
}
```

- `sessdata`：B 站登录 cookie（浏览器登录后从 Cookie 复制），可提升音质。
- `proxy`：需要代理访问 B 站时填写。
- `ffmpeg_path`：显式指定系统 ffmpeg，优先于内嵌版本。

## 项目文档

- 需求与调研：[idea.md](idea.md) ｜ 技术方案：[PLAN.md](PLAN.md) ｜ 开发日志：[docs/devlog](docs/devlog/)
