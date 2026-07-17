from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import decode_token


def error_response(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def get_current_user(
    authorization: str | None = Header(default=None), db: Session = Depends(get_db)
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise error_response(401, "AUTH_REQUIRED", "缺少认证令牌")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token)
    except ValueError:
        raise error_response(401, "TOKEN_INVALID", "令牌无效")
    username = payload.get("sub")
    if not username:
        raise error_response(401, "TOKEN_INVALID", "令牌无效")
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if not user:
        raise error_response(401, "USER_NOT_FOUND", "用户不存在或已禁用")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise error_response(403, "PERMISSION_DENIED", "仅管理员可执行此操作")
    return user
