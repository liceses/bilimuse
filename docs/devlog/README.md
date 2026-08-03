# 开发日志

边写代码边留痕。每篇自包含、可检索、可复用。

## 功能索引

| 日期 | 功能 | 里程碑 | 说明 |
|---|---|---|---|
| 2026-08-03 | [调研与总体方案](2026-08-03-调研与总体方案.md) | M0 | 立项调研、技术选型、差异化定位 |
| 2026-08-03 | [Bilibili 客户端](2026-08-03-bilibili-client.md) | M1 | Wbi 签名、搜索、view、playurl DASH 音频流 |
| 2026-08-03 | [下载与转码](2026-08-03-download.md) | M2 | DASH 下载、m4a直拷/mp3-flac转码、命名、SQLite 去重 |

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
