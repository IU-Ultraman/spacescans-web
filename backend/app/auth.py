# backend/app/auth.py
from datetime import datetime, timedelta, timezone
import bcrypt
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import app.config
from app.database import get_db
import sqlite3

# Sprint 12 G2: auto_error=False so a missing Authorization header reaches
# get_current_user, which raises 401 to match the rest of the API. With the
# default auto_error=True, FastAPI's security layer rejects the request with
# 403 before get_current_user runs — inconsistent with /api/tasks/* and the
# rest of the auth contract.
security = HTTPBearer(auto_error=False)

_BCRYPT_MAX_BYTES = 72


def _to_bcrypt_input(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_bcrypt_input(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(_to_bcrypt_input(plain), hashed.encode("utf-8"))

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=app.config.settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, app.config.settings.SECRET_KEY, algorithm=app.config.settings.ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    # Sprint 12 G2: HTTPBearer is configured with auto_error=False, so a
    # missing/empty Authorization header arrives here as None — translate to
    # 401 (the contract every other endpoint already returns).
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, app.config.settings.SECRET_KEY, algorithms=[app.config.settings.ALGORITHM])
        user_id = payload.get("sub")
        email = payload.get("email")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"id": int(user_id), "email": email}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
