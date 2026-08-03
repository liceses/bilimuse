# Bilibili 客户端 开发日志

- 日期：2026-08-03
- 里程碑：M1
- 关联：PLAN.md M1

## 目标与验收

- 目标：实现 B 站核心 API 客户端：Wbi 签名、视频搜索、视频信息（view/pagelist）、播放地址（DASH 纯音频流）
- 验收标准：
  - 搜索"歌名+歌手"能返回 B 站视频版本列表（bvid/标题/UP主/时长/播放量/封面）✅
  - playurl 能拿到 DASH 纯音频流 URL（未登录降级到基础音质）✅
  - typer 命令 `musicalbili search "关键词"` 能列出结果 ✅

## 方案与思路（含否决方案）

- 方案 A：用现成库 `bilibili-api-python`。否决：更新慢、Wbi/风控适配不全；本项目后续要深度定制，自持客户端更可控。
- 方案 B：自实现 Wbi 签名 + httpx 异步客户端（选定）。理由：httpx 原生 async、可统一注入 buvid3/UA/Referer 处理风控。
- 搜索接口：wbi 版 `x/web-interface/wbi/search/type` vs 旧版 `x/web-interface/search/type`。
  - 实测 wbi 版在本机（未登录、新会话）返回 `code=0` 但 `data` 只有 `v_voucher`（风控凭证，无 `result`）；**旧版直接可用**，故最终用旧版（无需签名）。

## 技巧

- 访问 B 站任何 API 前先 GET 一次 `https://www.bilibili.com/` 拿 `buvid3`/`b_nut` cookie，否则接口被 -412 拦截 → `musicalbili/providers/bilibili.py:47`
- 请求须带浏览器 UA + `Referer: https://www.bilibili.com/`，httpx 必须 `trust_env=False`（见踩坑）→ `bilibili.py:27`
- playurl 用 `fnval=4048` 一次性返回全部可用 DASH 流（含 flac/dolby），免多次探测 → `bilibili.py:146`
- `httpx.AsyncClient` 传入 `cookies=dict` 会转成 CookieJar 并自动保存 Set-Cookie，跨请求复用 → `bilibili.py:30`
- Windows 控制台显示中文乱码：运行前 `$env:PYTHONIOENCODING='utf-8'`（数据本身 UTF-8 正确，仅控制台 GBK 显示问题）

## API / 库 速查

- `httpx.AsyncClient`：异步 HTTP；`trust_env=False` 关键参数（禁环境/注册表代理）；`cookies=`、`follow_redirects=` → `bilibili.py:27`
- `GET x/web-interface/search/type?search_type=video&keyword=&order=click&page_size=`：视频搜索（旧版，无需 wbi）；`data.result[]` 含 `bvid/author/mid/pic/duration/play/tid/typename/title`；标题带 `<em class="keyword">` 高亮需剥除 → `bilibili.py:112`
- `GET x/web-interface/view?bvid=`：视频信息；`data.cid`（首 P cid）、`data.owner.name/mid`、`data.pages[]` → `bilibili.py:135`
- `GET x/player/pagelist?bvid=`：分 P 列表；`data[].cid/page/part/duration` → `bilibili.py:143`
- `GET x/player/wbi/playurl?fnval=4048&fourk=1&bvid=&cid=`：播放流（需 Wbi 签名）；`data.dash.audio[]`（AAC，`id/bandwidth/baseUrl`）、`data.dash.flac`（会员 30251）、`data.dash.dolby`（30250）→ `bilibili.py:146`
- Wbi 签名：img_key+sub_key 前 32 位作 mixin_key，过滤非 `\w` 键、排序、加 `wts`、urlencode(quote_plus)+mixin_key 做 MD5 → `bilibili.py:76`

## 踩坑

1. **URL 拼接漏斜杠 → 主机变成 `api.bilibili.comx`**
   现象：所有 API 调用报 `getaddrinfo failed`，偶发（其实必现，只有 nav 用对了）。
   原因：`API = "https://api.bilibili.com"` 无尾斜杠，`f"{API}{path}"` 且 `path="x/web-interface/..."` 无头斜杠 → 拼成 `https://api.bilibili.comx/...`。
   解决：`f"{API}/{path.lstrip('/')}"` → `bilibili.py:94`。
2. **wbi 搜索端点被风控，仅返回 `v_voucher`**
   现象：`x/web-interface/wbi/search/type` 返回 `code=0` 但 `data` 只有 `v_voucher` 字段，无 `result`。
   原因：未登录新会话触发风控凭证，可能还需更多指纹 cookie。
   解决：改用旧版 `x/web-interface/search/type`（无需签名，实测直接返回结果）→ `bilibili.py:112`。
3. **httpx 0.28 在 Windows 自动读取注册表代理**
   现象：请求走 `http://127.0.0.1:10808`（用户系统代理）导致 TLS 连接失败，但 `Get-ChildItem Env:` 查不到任何代理。
   原因：httpx 新版在 Windows 从 WinINET 注册表读取系统代理（`get_environment_proxies` 返回 `{'http://': 'http://127.0.0.1:10808', ...}`），与旧版仅读环境变量不同。
   解决：`trust_env=False`，代理改为 config 显式 `proxy` 字段 → `bilibili.py:34`、`musicalbili/config.py:26`。
4. **搜索标题含 HTML 高亮标签**
   现象：标题里出现 `<em class="keyword">周杰伦</em>`。
   解决：`re.sub(r"<[^>]+>", "", s)` → `bilibili.py:216`。
5. **控制台中文乱码（显示层）**
   现象：PowerShell 下输出 `�ܽ���`。
   原因：Windows 控制台 GBK 代码页，Python 输出 UTF-8 中文显示为乱码。
   解决：`$env:PYTHONIOENCODING='utf-8'`（仅影响显示，数据正确）。

## 验证

- `python -m musicalbili search "周杰伦 晴天" --limit 5`：返回 5 条 B 站版本（BV号/分区/时长/播放量/UP主/标题/封面）✅
- `python -m musicalbili info BV1d4411N7zD`：标题、作者、cid、分 P 列表 ✅
- playurl 实测：3 条 AAC 轨（30216/30232/30280），`pick_audio` 选中最高码率 30280，未登录无 flac/dolby ✅
- `python -m pytest tests -q`：2 passed ✅
- `python -m ruff check musicalbili tests`：All checks passed ✅
