"""
图片本地缓存管理器：负责对 QQ / OneBot11 多模态图片进行本地持久化，
防止 QQ CDN 的 rkey/fileid 短效签名过期导致图片在 WebUI 无法加载或闪烁。
"""

import asyncio
import hashlib
import os
import shutil
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote, unquote

import httpx

IMAGE_CACHE_DIR = Path("cache/images")
IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class ImageCacheManager:
    def __init__(self, cache_dir: Path = IMAGE_CACHE_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_filename(self, url: str) -> str:
        h = hashlib.md5(url.encode("utf-8")).hexdigest()
        ext = ".jpg"
        clean_url = url.split("?")[0].lower()
        if clean_url.endswith(".gif") or "raw300.gif" in url:
            ext = ".gif"
        elif clean_url.endswith(".png"):
            ext = ".png"
        elif clean_url.endswith(".webp"):
            ext = ".webp"
        return f"{h}{ext}"

    def get_local_path(self, url: str) -> Path:
        filename = self._get_filename(url)
        return self.cache_dir / filename

    def get_local_url(self, url: str) -> str:
        """如果本地已成功缓存该图片，则返回本地路由；否则返回代理/本地带 remote 兜底路由。"""
        if not url:
            return ""
        if url.startswith("/api/cache/image/"):
            return url
        filename = self._get_filename(url)
        target = self.cache_dir / filename
        if target.exists() and target.stat().st_size > 0:
            return f"/api/cache/image/{filename}"
        
        # 若尚未写入，返回带 remote 兜底代理，避免前端直接向腾讯 CDN 请求因 Referer 防盗链返回 403
        return f"/api/cache/image/{filename}?remote={quote(url)}"

    async def cache_image_async(self, url: str, expected_filename: Optional[str] = None) -> Optional[str]:
        """异步拉取或复制图片并缓存到本地。返回本地相对 API 路径。"""
        if not url:
            return None

        filename = expected_filename or self._get_filename(url)
        target = self.cache_dir / filename
        if target.exists() and target.stat().st_size > 0:
            return f"/api/cache/image/{target.name}"

        # 1. 尝试作为本地绝对路径/file://协议解析
        try:
            local_candidate = url
            if local_candidate.startswith("file:///"):
                local_candidate = unquote(local_candidate[8:])
            elif local_candidate.startswith("file://"):
                local_candidate = unquote(local_candidate[7:])
            local_p = Path(local_candidate)
            if local_p.exists() and local_p.is_file() and local_p.stat().st_size > 0:
                shutil.copyfile(local_p, target)
                return f"/api/cache/image/{target.name}"
        except Exception:
            pass

        # 2. 如果是 HTTP/HTTPS 网络直链，使用防盗链头发起请求
        if url.startswith("http://") or url.startswith("https://"):
            headers_list = [
                {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://qzone.qq.com/",
                    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                },
                {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://qun.qq.com/",
                    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                },
                {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "*/*",
                },
            ]
            for headers in headers_list:
                try:
                    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
                        resp = await client.get(url)
                        if resp.status_code == 200 and len(resp.content) > 0:
                            # 保证请求的文件名目标一定落地
                            target.write_bytes(resp.content)

                            # 同时根据 Content-Type 记录真实后缀
                            ctype = resp.headers.get("Content-Type", "")
                            h = hashlib.md5(url.encode("utf-8")).hexdigest()
                            if "gif" in ctype:
                                (self.cache_dir / f"{h}.gif").write_bytes(resp.content)
                            elif "png" in ctype:
                                (self.cache_dir / f"{h}.png").write_bytes(resp.content)
                            elif "webp" in ctype:
                                (self.cache_dir / f"{h}.webp").write_bytes(resp.content)

                            return f"/api/cache/image/{target.name}"
                except Exception as e:
                    continue

        # 3. 若非 http 且为 OneBot 文件 ID / 文件哈希，尝试通过 OneBot get_image API 换取真实直链或本地文件
        try:
            from src.onebot import onebot_client
            if onebot_client.is_connected:
                res = await onebot_client.call_api("get_image", {"file": url})
                if res and res.get("data"):
                    remote_url = res["data"].get("url")
                    local_file = res["data"].get("file")
                    if remote_url and remote_url.startswith("http") and remote_url != url:
                        return await self.cache_image_async(remote_url, expected_filename=filename)
                    elif local_file and local_file != url:
                        return await self.cache_image_async(local_file, expected_filename=filename)
        except Exception:
            pass

        return None

    async def cache_images_async(self, urls: List[str]):
        """并发缓存一批图片。"""
        if not urls:
            return
        tasks = [self.cache_image_async(u) for u in urls if u]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


image_cache_manager = ImageCacheManager()
