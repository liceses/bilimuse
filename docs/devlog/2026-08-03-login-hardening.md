# B站扫码登录 与 API 加固 开发日志

- 日期：2026-08-03
- 里程碑：M3 补充（登录降风控 + 抗失效加固）
- 关联：[M1 客户端](2026-08-03-bilibili-client.md)、[M3 元数据](2026-08-03-metadata-tagger.md)

## 目标与验收

- 目标：B 站扫码登录降风控；消除红级接口风险（B站搜索单端点、网易云仅明文旧版）
- 验收标准：
  - `bilimuse login` 终端二维码 → 手机扫码 → SESSDATA 写入 config
  - 登录后 B 站搜索优先 wbi 端点、不再 v_voucher；失败自动回退旧版
  - 网易云明文失败时自动降级 weapi 兜底
  - `doctor --network` 逐源探测连通性
  - `logout` 清除登录态

## 方案与思路（含否决方案）

- B 站降风控：**扫码登录**（passport web qrcode，Bilibili-Evolved / bilibili-api-python 同套），比手动填 SESSDATA 更安全便捷。
- B 站搜索加固：`search_video` **双端点**——登录态优先 `wbi/search/type`，空 result/v_voucher/-412 时回退旧版 `search/type`。
- 网易云加固：明文旧版为快速路径，失败/空 → **weapi**（AES-CBC + RSA，官方网页主链路，长期稳定）。
- 否决：只依赖公共 API 镜像（第三方托管不可控）。

## 技巧

- `qrcode.QRCode().print_ascii(invert=True)`：终端渲染二维码，无需 PIL → `bilimuse/services/auth.py:22`
- passport `qrcode/poll` 的**外层 `code` 恒为 0**（请求成功），真实状态在 `data.code`（86101 未扫 / 86090 待确认 / 0 成功带 Set-Cookie / 86038 过期）→ `auth.py:57`
- SESSDATA 提取：`set-cookie` 头按 `;` 拆分找 `SESSDATA=` → `auth.py:27`
- B 站搜索双端点：登录态先试 wbi，`data.get("result")` 为空即 v_voucher 风控，回退旧版 → `providers/bilibili.py:119`
- 网易云 weapi 兜底：`try: legacy; if songs: return; except: pass` → `providers/meta.py:101`
- **weapi 的 AES/RSA 无需 cryptography 的 RSA 模块**：RSA 用大整数 `pow(text_int, e, n)`，只用 `cryptography` 的 AES-CBC → `meta.py:33`

## API / 库 速查

- `GET passport.bilibili.com/x/passport-login/web/qrcode/generate`：拿 `data.url`（二维码内容）+ `data.qrcode_key` → `auth.py:44`
- `GET .../qrcode/poll?qrcode_key=`：轮询；成功时响应 `Set-Cookie: SESSDATA=...` → `auth.py:58`
- `POST music.163.com/weapi/search/get/web`（weapi 搜索）：`data=_weapi_params({s,type,limit,offset,csrf_token})`，返回 `result.songs[]` → `meta.py:119`
- `POST music.163.com/weapi/v3/song/detail`：weapi 取封面；**键是 `al`/`ar`** 而非 `album`/`artists` → `meta.py:156`
- `cryptography.hazmat.primitives.ciphers` AES-CBC：`algorithms.AES + modes.CBC(iv)` → `meta.py:23`
- `qrcode`：`QRCode().add_data(url).make().print_ascii(invert=True)` → `auth.py:22`

## 踩坑

1. **weapi 端点选错 → code 50000005**
   现象：`weapi/cloudsearch/get/web` 返回 `{"code": 50000005}`，无 `result`。
   原因：cloudsearch 端点已废弃/被拦；`weapi/search/get/web` 正常。
   解决：改用 `weapi/search/get/web` → `meta.py:119`。
2. **weapi v3 song/detail 结构不同**
   现象：`songs[0].album` 为 None，封面拿不到。
   原因：weapi v3 返回 `al`/`ar` 键（旧接口是 `album`/`artists`）。
   解决：`_pic_from_songs`/`_parse_songs` 兼容 `album or al`、`artists or ar` → `meta.py:170`。
3. **poll 外层 code 误导**
   现象：探测时 `poll` 外层 `code=0` 误以为登录成功。
   原因：外层 0 仅表示请求成功；真实状态在 `data.code`。
   解决：判 `data.code` → `auth.py:60`。

## 验证

- `bilimuse doctor --network`：B站搜索 OK / 咪咕 OK(20) / 网易云 OK(源=netease) ✅
- weapi 搜索实测：`weapi/search/get/web` 返回 3 条；封面 `_cover_weapi` 返回 `p1.music.126.net/...` ✅
- 扫码登录冒烟：generate → 终端渲染二维码 → 轮询 → 超时抛 `LoginError 登录超时`（完整链路通，待真人扫码验证）✅
- B 站搜索回归（未登录→旧版）：`doctor --network` B站搜索 OK ✅
- `python -m pytest tests -q`：21 passed ✅
- `python -m ruff check bilimuse tests`：All checks passed ✅

