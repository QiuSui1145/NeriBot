"""WebUI 登录鉴权与 Session Token 管理模块。
使用安全的 HMAC-SHA256 签名，无第三方臃肿依赖。
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import config_manager

security_scheme = HTTPBearer(auto_error=False)


def generate_token(username: str, expires_in_seconds: int = 86400 * 7) -> str:
    """生成包含过期时间的 HMAC 签名令牌。"""
    secret = config_manager.config.security.jwt_secret.encode("utf-8")
    payload = {
        "sub": username,
        "exp": int(time.time()) + expires_in_seconds,
        "iat": int(time.time()),
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    signature = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def verify_token(token: str) -> Optional[dict]:
    """校验令牌有效性与签名。"""
    if not token or "." not in token:
        return None
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, signature = parts
        secret = config_manager.config.security.jwt_secret.encode("utf-8")
        expected_sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None

        # 补齐 base64 padding
        padded_b64 = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded_b64.encode("utf-8")).decode("utf-8"))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


async def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> str:
    """FastAPI 路由依赖：要求登录状态。支持 Authorization Bearer 头及 Cookie。"""
    token = None
    if credentials:
        token = credentials.credentials
    elif "access_token" in request.cookies:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录系统",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录状态已失效或已过期，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload["sub"]
