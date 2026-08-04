"""B 站扫码登录：QR generate → 终端渲染 → 轮询 poll → 提取 SESSDATA。"""

from __future__ import annotations

import asyncio

import httpx
import qrcode

from ..config import Config

PASSPORT = "https://passport.bilibili.com/x/passport-login/web/qrcode"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class LoginError(RuntimeError):
    pass


def show_qr(url: str) -> None:
    """终端渲染二维码。"""
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)


def _extract_cookie(set_cookie: str, name: str) -> str:
    for part in set_cookie.split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v
    return ""


async def bili_login(config: Config | None = None, poll_interval: float = 2.0, timeout: float = 180.0) -> str:
    """执行扫码登录，返回 SESSDATA。"""
    config = config or Config.load()
    async with httpx.AsyncClient(
        headers={"User-Agent": config.ua or UA},
        follow_redirects=True,
        timeout=httpx.Timeout(20.0, connect=10.0),
        trust_env=False,
        proxy=config.proxy or None,
    ) as client:
        r = await client.get(f"{PASSPORT}/generate")
        r.raise_for_status()
        data = r.json().get("data") or {}
        url, key = data.get("url", ""), data.get("qrcode_key", "")
        if not url or not key:
            raise LoginError("获取二维码失败")

        show_qr(url)
        deadline = asyncio.get_event_loop().time() + timeout
        last_note = ""
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(poll_interval)
            r = await client.get(f"{PASSPORT}/poll", params={"qrcode_key": key})
            body = r.json()
            code = (body.get("data") or {}).get("code")
            if code == 0:
                sessdata = _extract_cookie(r.headers.get("set-cookie", ""), "SESSDATA")
                if sessdata:
                    return sessdata
                raise LoginError("登录成功但未取到 SESSDATA")
            if code == 86090:
                if last_note != "confirmed":
                    print("已扫码，请在手机上确认登录...")
                    last_note = "confirmed"
            elif code == 86038:
                raise LoginError("二维码已过期，请重新运行 login")
            # 86101 = 未扫码，继续轮询
        raise LoginError("登录超时")
