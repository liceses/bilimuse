# 开发日志

边写代码边留痕。每篇自包含、可检索、可复用。

## 功能索引

| 日期 | 功能 | 里程碑 | 说明 |
|---|---|---|---|
| 2026-08-03 | [调研与总体方案](2026-08-03-调研与总体方案.md) | M0 | 立项调研、技术选型、差异化定位 |
| 2026-08-03 | [Bilibili 客户端](2026-08-03-bilibili-client.md) | M1 | Wbi 签名、搜索、view、playurl DASH 音频流 |
| 2026-08-03 | [下载与转码](2026-08-03-download.md) | M2 | DASH 下载、m4a直拷/mp3-flac转码、命名、SQLite 去重 |
| 2026-08-03 | [元数据反查与打标签](2026-08-03-metadata-tagger.md) | M3 | 咪咕/网易云多源反查、mutagen 打标签、webp封面转换 |
| 2026-08-03 | [扫码登录与 API 加固](2026-08-03-login-hardening.md) | M3补 | B站扫码登录降风控、搜索双端点、网易云 weapi 兜底 |
| 2026-08-03 | [歌词获取与校准](2026-08-03-lyric-align.md) | M4 | LRCLIB/网易云/B站字幕多源降级、快速校准、lyric-align 强制对齐 |
| 2026-08-04 | [pipeline 闭环 + 搜索 + TUI](2026-08-04-pipeline-tui.md) | M5 | get 一键闭环、网易云歌词正文反查、Textual TUI |
| 2026-08-04 | [Web 界面](2026-08-04-web.md) | M6 | FastAPI + WebSocket 进度、原生单页、[web] extra |

## 技术沉淀速查表

| 技巧/坑 | 一句话 | 位置 |
|---|---|---|
| URL 拼接 | `f"{API}/{path.lstrip('/')}"`，API 常量忘加尾斜杠会拼成 `api.bilibili.comx` | `musicalbili/providers/bilibili.py:94` |
| Wbi 签名 | 播放接口需 wbi 签名 + buvid3 cookie 防 -412 | `musicalbili/providers/bilibili.py:76` |
| wbi 搜索被风控 | wbi 搜索端点未登录返回 `v_voucher` 无结果，用旧版 `search/type` | `bilibili.py:112` |
| httpx 系统代理 | httpx 0.28 在 Windows 读注册表 WinINET 代理，需 `trust_env=False` | `bilibili.py:34` |
| 控制台乱码 | `$env:PYTHONIOENCODING='utf-8'`，数据本身 UTF-8 正确 | 仅显示层 |
| typer 0.27 Exit | `Exit` 只有 `code` 参数，错误信息先 `echo` 再 `Exit(code=1)` | `musicalbili/cli.py:79` |
| 下载前查 ffmpeg | 需转码时先 `shutil.which` 再下载，避免半途失败 | `musicalbili/services/download.py:87` |
| SQLite 去重 | `UNIQUE(bvid,cid)` + `INSERT OR REPLACE` 幂等 | `musicalbili/db.py:38` |
| ffmpeg 内嵌 | `imageio-ffmpeg` 可选 extra，PyPI 拉取不经 GitHub；`find_ffmpeg` config→PATH→内置 | `musicalbili/services/download.py:32` |
| ffmpeg 路径三级回退 | `config.ffmpeg_path` → `shutil.which` → `imageio_ffmpeg.get_ffmpeg_exe()`（懒 import） | `download.py:32` |
| mock 未装包 | `setitem(sys.modules,'pkg',None)` 让 `import` 抛 ImportError，模拟未安装 | `tests/test_download.py:44` |
| 网易云无周杰伦版权 | 2018 授权到期，搜索只剩翻唱/remix → 咪咕 MIGUM2.0 为第一源 | `musicalbili/providers/meta.py` |
| 咪咕封面 | 用搜索结果 `imgItems` URL（勿按 id 再搜），webp 用 ffmpeg 管道转 jpeg | `meta.py:96` |
| 标题清洗/匹配 | `clean_title`+`split_query` 拆歌手/歌名，歌手命中±分 | `musicalbili/services/tagger.py:30` |
| B站扫码登录 | passport qrcode generate/poll；外层 code=0 恒真，看 `data.code`；成功从 Set-Cookie 取 SESSDATA | `musicalbili/services/auth.py` |
| B站搜索双端点 | 登录态优先 wbi，`result` 空(v_voucher)自动回退旧版 | `musicalbili/providers/bilibili.py:119` |
| 网易云 weapi | 端点用 `weapi/search/get/web`（cloudsearch 已 50000005）；v3 详情用 `al`/`ar` 键 | `musicalbili/providers/meta.py:119` |
| 登录降风控 | 匿名流量是 B 站风控重点，SESSDATA 后走 wbi 主链路 | 风险表 |
| fMP4 时长 | mutagen 读分片 MP4 时长为 0，用 ffmpeg `-i -f null -` 解析 Duration | `musicalbili/services/aligner.py:38` |
| whisper 模型国内下载 | hf-mirror 极慢，ModelScope 镜像官方 faster-whisper 快；`whisper_model` 支持本地路径 | `aligner.py:107` |
| lyric-align 编码 | Windows GBK 读崩 UTF-8 歌词 → 子进程 `PYTHONUTF8=1` | `aligner.py:111` |
| LRC 清理 | 网易云剥作曲/编曲头；LRCLIB 剥空行/live标题行；翻译合并 | `musicalbili/services/lyric.py` |
| align 置信度回退 | `-f json --interpolate` 取 matched 标记；匹配率<50% 回退原歌词，不盲目缩放 | `musicalbili/services/aligner.py` |
| 语言自动检测 | 假名→ja 决定性；咪咕 tags 网络信号；`whisper_language` 兜底。勿硬编码 zh | `aligner.py` / `providers/meta.py` |
| 锚点线性拟合 | matched<50% 但锚点≥3 时最小二乘 `aligned=a·source+b` 整体变换（治前留白） | `aligner.py:_apply_alignment` |
| 稳健拟合 | 锚点偏移 MAD≤3s 判纯平移（中位数），否则 LSQ；防离群点带偏 | `aligner.py:_robust_fit` |
| 外文歌译文 | 主源非netease，detect非zh → 网易云双语对替换（`_from_netease_bilingual`） | `lyric.py` |
| 译文配对 | 校准前按时间戳 pair_translation（英文/拟声行→None），校准后 reattach 按行序贴回；勿行序1:1 | `lyric.py:pair_translation`/`reattach_translation` |
| 歌词正文搜索 | 网易云 weapi `s` 参数即按歌词搜（返回歌名对、歌手是翻唱者）；LRCLIB 不搜歌词正文 | `services/search.py` |
| pipeline 事件化 | 编排抽 `services/pipeline.py`，on_event 推 info/progress/meta/lyric，CLI/TUI/Web 复用 | `pipeline.py` |
| Textual 8 | `Input.action_submit()` 是协程需 await；headless 用 `run_test`+`pilot.pause()` | `tui.py` |
| `「」`/`《》`歌名提取 | `split_query` 优先括号内歌名（日式引号），再 ` - ` 分隔 | `musicalbili/services/tagger.py` |
