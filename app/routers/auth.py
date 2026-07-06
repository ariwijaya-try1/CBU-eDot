from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.schemas.auth import LoginRequest, RegisterRequest
from app.database.database import get_db
from app.models.user import User
from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    verify_access_token,
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter()
security = HTTPBearer()

@router.post("/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):

    user = User(
        fullname=data.fullname,
        email=data.email,
        password=hash_password(data.password)
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "message": "Register berhasil",
        "user": user.id
    }

@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):

    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        return {
            "message": "Email tidak ditemukan"
        }

    if not verify_password(data.password, user.password):
        return {
            "message": "Password salah"
        }

    token = create_access_token(
    {
        "sub": user.email
    }
    )

    return {
        "message": "Login berhasil",
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "fullname": user.fullname,
            "email": user.email
        }
    }

@router.get("/me")
def get_me(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):

    token = credentials.credentials

    email = verify_access_token(token)

    if not email:
        return {
            "message": "Token tidak valid"
        }

    user = db.query(User).filter(
        User.email == email
    ).first()

    if not user:
        return {
            "message": "User tidak ditemukan"
        }

    return {
        "id": user.id,
        "fullname": user.fullname,
        "email": user.email
    }