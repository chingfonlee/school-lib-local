from fastapi import APIRouter, Request, HTTPException
from passlib.hash import bcrypt
from pydantic import BaseModel

from app.database import get_connection

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(req: LoginRequest, request: Request):
    conn = get_connection()
    user = conn.execute(
        "SELECT id, password_hash, display_name FROM users WHERE username = ?",
        (req.username,),
    ).fetchone()
    conn.close()
    if user is None or not bcrypt.verify(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    request.session["user_id"] = user["id"]
    request.session["display_name"] = user["display_name"]
    return {"user_id": user["id"], "display_name": user["display_name"]}


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="未登入")
    return {"user_id": user_id, "display_name": request.session.get("display_name")}
