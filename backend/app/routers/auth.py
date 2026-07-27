# backend/app/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException
from app.schemas import (
    UserCreate,
    LoginRequest,
    ChangePasswordRequest,
    Token,
    ErrorResponse,
)
from app.auth import hash_password, verify_password, create_access_token
from app.database import get_db
import sqlite3

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/signup", response_model=Token)
def signup(user: UserCreate, db: sqlite3.Connection = Depends(get_db)):
    hashed = hash_password(user.password)
    try:
        cursor = db.execute(
            "INSERT INTO users (email, hashed_password, first_name, last_name) VALUES (?, ?, ?, ?)",
            (user.email, hashed, user.first_name, user.last_name)
        )
        db.commit()
        user_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Email already registered")
    token = create_access_token({"sub": str(user_id), "email": user.email})
    return Token(access_token=token)

@router.post("/login", response_model=Token)
def login(credentials: LoginRequest, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT id, hashed_password FROM users WHERE email = ?", (credentials.email,)).fetchone()
    if not row or not verify_password(credentials.password, row["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": str(row["id"]), "email": credentials.email})
    return Token(access_token=token)

@router.post("/change-password", response_model=Token)
def change_password(req: ChangePasswordRequest, db: sqlite3.Connection = Depends(get_db)):
    # Self-service: identity is proven by the current password, so no login /
    # JWT is required (the form lives on the public login page). No email infra,
    # so this cannot help a *forgotten* password — that path stays admin-reset.
    row = db.execute(
        "SELECT id, hashed_password FROM users WHERE email = ?", (req.email,)
    ).fetchone()
    if not row or not verify_password(req.current_password, row["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not req.new_password:
        raise HTTPException(status_code=400, detail="New password must not be empty")
    db.execute(
        "UPDATE users SET hashed_password = ? WHERE id = ?",
        (hash_password(req.new_password), row["id"]),
    )
    db.commit()
    # Issue a fresh token so the user is signed in with the new password.
    token = create_access_token({"sub": str(row["id"]), "email": req.email})
    return Token(access_token=token)
