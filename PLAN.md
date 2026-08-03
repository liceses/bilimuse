# MusicalBILI 技术方案

## 目标

B 站深度定制的音乐下载器：输入歌名/歌手/**歌词片段** → 反查真实歌曲 → B 站搜索选版本 → 下载纯音频 → 自动打标签 → 自动配歌词 → **自动校准时间轴** → 内嵌封面。单曲一键闭环优先，CLI 与 Web 双界面。

差异化点（现有项目均无）：
1. **按歌词全文反查歌曲**（歌词库 → 歌名 → B 站选版本）
2. **歌词时间轴自动校准**（whisper 强制对齐 + 指纹/时长偏移校正）

## 技术栈

- Python 3.11+
- `httpx`（异步 HTTP + 自定义 Wbi 签名）
- `pydantic` v2（数据模型）
- `mutagen`（ID3 / FLAC / MP4 打标签 + 内嵌封面歌词）
- `lyric-align` + `faster-whisper`（歌词强制对齐校准）
- `audio-offset-finder`（整体偏移校正，可选）
- ffmpeg（可选内嵌）：**`imageio-ffmpeg` 作为可选 extra** 打包静态 ffmpeg，`pip install -e ".[ffmpeg]"` 即装即用，不依赖用户系统环境；纯 m4a 用户可零依赖
- `qrcode`（纯 Python，终端渲染 B 站扫码登录二维码）
- `cryptography`（网易云 **weapi** 兜底端点：AES+RSA 签名）
- CLI：`typer`（基础命令）+ `textual`（交互式搜索/选版本）
- Web：`fastapi` + 单页前端（挂核心库，二期）
- 部署：`setup.ps1` / `setup.sh` 一键装依赖；`musicalbili doctor` 检测环境

## 目录结构

```
MusicalBILI/
├── pyproject.toml
├── musicalbili/
│   ├── __init__.py
│   ├── __main__.py
│   ├── config.py        # 下载目录/格式/cookie/文件名模板/校准开关
│   ├── models.py        # Song/Version/Lyric/TagInfo
│   ├── db.py            # SQLite 下载历史与去重
│   ├── providers/
│   │   ├── bilibili.py  # wbi签名/搜索/view/playurl/字幕
│   │   ├── lyrics.py    # LRCLIB/网易云/QQ/B站AI字幕
│   │   └── meta.py      # 网易云反查真实 歌名/歌手/专辑/封面/时长
│   ├── services/
│   │   ├── auth.py       # B站扫码登录（QR generate/poll → SESSDATA）
│   │   ├── search.py    # 两跳反查：歌词→歌曲→B站版本
│   │   ├── download.py  # DASH音频流下载 + 转码
│   │   ├── tagger.py    # mutagen 写标签 + 内嵌
│   │   ├── lyric.py     # 歌词获取与匹配（按源降级）
│   │   └── aligner.py   # 时间轴校准
│   ├── pipeline.py      # 一键闭环编排
│   ├── cli.py           # typer 命令 + textual 交互
│   └── web.py           # FastAPI（二期）
├── tests/
├── setup.ps1        # Windows 一键部署（venv + 依赖，可选装 ffmpeg）
├── setup.sh         # Linux/macOS 一键部署
└── README.md
```

## 数据流（一键闭环 pipeline）

```
输入 query（歌名/歌手/歌词片段）
   │
   ▼
[1] search.search()：两跳反查
    ├─ 若为歌词片段：Musixmatch/LRCLIB → 候选歌曲(title+artist+duration)
    └─ B站 wbi/search/type (video) 按 <title> <artist> 搜
        过滤：hit_columns 含 title、音乐分区、时长相近 → 版本列表
   │
   ▼
[2] 用户选版本 → bvid + cid
   │
   ▼
[3] meta 反查：咪咕 MIGUM2.0 → 网易云（兜底），真实歌名/歌手/专辑/封面
   │
   ▼
[4] download：x/player/wbi/playurl(fnval=4048) → DASH audio
    ├─ 质量选择：VIP→flac(30251)/dolby(30250)，否则最高 AAC
    └─ m4s→ m4a(直拷) / mp3 / flac(ffmpeg 转码)
   │
   ▼
[5] lyric.fetch：LRCLIB → 网易云 → QQ → B站AI字幕(兜底)
   │
   ▼
[6] aligner.calibrate(audio, lrc)：
    ├─ 快速：歌词末行时间 vs 音频时长 → 整体偏移/缩放（写 [offset:]）
    └─ 精确（可选）：lyric-align(faster-whisper) 强制对齐 → 新 LRC
   │
   ▼
[7] tagger.tag_and_embed：
    ├─ mutagen 写 TIT2/TPE1/TALB/APIC/USLT
    ├─ 内嵌封面 + 歌词，侧车同名 .lrc
    └─ 命名模板：{artist} - {title}.{ext}；db 记录去重
```

## 歌词来源降级链

1. **LRCLIB**：`/api/get`（track+artist+album+duration 签名匹配），免费无 key，标准 LRC
2. **网易云**：weapi `cloudsearch/get/web` + `song/lyric`（需逆向签名，AES+RSA）
3. **QQ 音乐**：client_search_cp + fcg_query_lyric_new
4. **B站 AI 字幕**：`x/player/wbi/v2`，用 `music` 置信度字段筛演唱段（仅兜底，质量差）

## 关键风险与对策

| 风险 | 对策 |
|---|---|
| B站搜索风控（匿名 v_voucher / -412） | **扫码登录降风控**（`musicalbili login` 存 SESSDATA）；搜索**双端点自动降级**：登录态优先 wbi → 失败回退旧版；Wbi 签名 + buvid3 + 合理 UA/Referer；失败重试+退避 |
| 网易云逆向接口变动 | **明文旧版 → weapi 双端点自动降级**（weapi 为官方网页主链路，长期稳定）；接口层抽象，多源降级；LRCLIB 为歌词主源避免主链路依赖逆向 |
| whisper 对歌唱识别不准 | 调参（关 VAD、CJK 阈值、必要时分离人声）；仅当快速校准无法收敛时启用 |
| ffmpeg 缺失 | ffmpeg 为可选 extra（imageio-ffmpeg 内嵌，PyPI 拉取不经 GitHub）；查找链 config→系统PATH→内置；缺失仅 mp3/flac 报错并给出安装指引，m4a 不受影响 |
| 高音质需会员 | 未登录/VIP 自动降级到可用最高音质，README 说明 |
| 接口失效（长期） | 逆向接口无法"确保"长期可用，设计为**抗失效**：多源冗余（咪咕+网易云）、每源多端点自动降级、`doctor --network` 逐源探测告警、接口适配集中并注释参考文档 |

## 部署

- **轻量（仅 m4a）**：`python -m venv .venv` + `pip install -e .`，无 ffmpeg 依赖。
- **完整（mp3/flac）**：`pip install -e ".[ffmpeg]"`，imageio-ffmpeg 从 PyPI（国内可用清华镜像）拉取 ~60MB 静态 ffmpeg 到 venv，装完即离线可用。
- `setup.ps1` / `setup.sh`：一键完成 venv + 依赖，`--with-ffmpeg` 开关加装完整模式。
- `musicalbili doctor`：检测 Python / ffmpeg（config→系统PATH→内置）/ 配置目录，输出修复指引。
- **登录降风控**：`musicalbili login` 手机扫码登录 B 站（存 SESSDATA），大幅降低搜索风控、提升音质、解锁 AI 字幕；`logout` 清除。

## 里程碑

- **M1** B站 client（wbi/搜索/view/playurl）+ typer 搜索列表展示
- **M2** 下载 + 转码 + 命名 + 去重入库
- **M3** 网易云元数据反查 + mutagen 打标签
- **M4** 歌词获取（多源降级）+ 校准（偏移/缩放 + lyric-align）
- **M5** pipeline 一键闭环 + textual 交互式界面
- **M6** FastAPI Web 界面

每阶段验证：M1 能搜出并列出 B 站版本；M2 生成带正确命名和时长的音频文件；M3 文件 ID3 完整；M4 歌词时间与音频吻合（抽查）；M5/M6 端到端一条命令/一次点击完成。
