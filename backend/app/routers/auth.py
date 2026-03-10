# backend/app/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException
from app.schemas import UserCreate, LoginRequest, Token, ErrorResponse
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
