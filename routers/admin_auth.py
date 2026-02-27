import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import COOKIE_SECURE, DOMAIN, SMTP_HOST
from core.email import send_email
from core.security import create_token, get_current_user, invalidate_token
from db.users import (
    authenticate_user,
    create_password_reset_token,
    get_user_profile,
    update_user_password,
    update_user_profile,
    use_password_reset_token,
    verify_password_reset_token,
)
from schemas import (
    ChangePasswordRequest,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    ProfileUpdateRequest,
)

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()


@router.get("/manage", response_class=HTMLResponse)
async def manage_page(request: Request):
    return templates.TemplateResponse("manage.html", {"request": request, "domain": DOMAIN})


@router.post("/api/manage/login")
@limiter.limit("5/minute")
async def manage_login(request: Request, data: LoginRequest):
    user = await authenticate_user(data.username, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = await create_token(user)
    response = JSONResponse({"user": user})
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="strict" if COOKIE_SECURE else "lax",
        max_age=86400,
        path="/",
    )
    return response


@router.post("/api/manage/logout")
@limiter.limit("20/minute")
async def manage_logout(request: Request):
    token = request.cookies.get("session_token")
    if token:
        await invalidate_token(token)
    response = JSONResponse({"success": True})
    response.delete_cookie("session_token", path="/")
    return response


@router.post("/api/manage/password-reset")
@limiter.limit("3/minute")
async def request_password_reset(request: Request, data: PasswordResetRequest):
    if not SMTP_HOST:
        raise HTTPException(status_code=503, detail="Password reset not available")

    result = await create_password_reset_token(data.username)
    if not result:
        return {"message": "If the user exists, a reset email will be sent"}

    token, _ = result
    reset_url = f"https://{DOMAIN}/manage/reset?token={token}"
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background: #08080f; color: white; padding: 20px;">
        <div style="max-width: 400px; margin: 0 auto; background: rgba(255,255,255,0.05); padding: 30px; border-radius: 15px;">
            <h2 style="text-align: center;">Password Reset</h2>
            <p>Click the button below to reset your password:</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{reset_url}" style="background: #9333ea; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; display: inline-block;">Reset Password</a>
            </div>
            <p style="font-size: 12px; color: #888;">This link expires in 1 hour.</p>
        </div>
    </body>
    </html>
    """
    send_email(f"{data.username}@{DOMAIN}", "Password Reset Request", body)
    return {"message": "If the user exists, a reset email will be sent"}


@router.post("/api/manage/password-reset/confirm")
@limiter.limit("5/minute")
async def confirm_password_reset(request: Request, data: PasswordResetConfirm):
    user_id = await verify_password_reset_token(data.token)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    await update_user_password(user_id, data.new_password)
    await use_password_reset_token(data.token)
    return {"message": "Password updated successfully"}


@router.post("/api/manage/change-password")
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    data: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    user = await authenticate_user(current_user["username"], data.old_password)
    if not user:
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    await update_user_password(current_user["id"], data.new_password)
    return {"message": "Password updated successfully"}


@router.get("/api/manage/profile")
@limiter.limit("30/minute")
async def manage_get_profile(request: Request, current_user: dict = Depends(get_current_user)):
    profile = await get_user_profile(current_user["id"])
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return profile


@router.put("/api/manage/profile")
@limiter.limit("30/minute")
async def manage_update_profile(
    request: Request,
    data: ProfileUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    success = await update_user_profile(current_user["id"], data.email)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Profile updated successfully", "email": data.email}
