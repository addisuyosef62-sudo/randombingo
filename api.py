import json
import os
import re
import urllib.error
import urllib.request
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from auth_utils import hash_password, verify_password, verify_telegram_init_data
from supabase_client import SupabaseError, supabase_request


app = FastAPI(title="Bingo Habesha API")
allowed_origin = os.environ.get("APP_ORIGIN", "").strip()
if allowed_origin:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[allowed_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Telegram-Init-Data"],
    )


class DepositRequest(BaseModel):
    amount: float = Field(ge=50, le=100_000)
    payment_method: Literal["TeleBirr", "CBE Birr"]
    payment_proof: str = Field(min_length=8, max_length=3_000)


class PasswordChange(BaseModel):
    current_password: str = Field(default="", max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class CouponRedemption(BaseModel):
    code: str = Field(min_length=4, max_length=32)


def telegram_user(init_data: str | None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token or not init_data:
        raise HTTPException(
            status_code=401,
            detail="Open this feature from the authenticated Telegram Mini App.",
        )
    try:
        return verify_telegram_init_data(init_data, token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def send_admin_message(text, request_id):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    admin_id = os.environ.get("TELEGRAM_ADMIN_ID", "")
    if not token or not admin_id:
        raise RuntimeError("Telegram admin notifications are not configured.")

    payload = {
        "chat_id": admin_id,
        "text": text,
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "Approve", "callback_data": f"webdep_{request_id}_approve"},
                {"text": "Reject", "callback_data": f"webdep_{request_id}_reject"},
            ]]
        },
    }
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Telegram admin notification could not be delivered.") from exc
    if not result.get("ok"):
        raise RuntimeError("Telegram admin notification was rejected.")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "Bingo Habesha API",
        "health": "/health",
        "docs": "/docs",
    }


@app.get("/api/payment-methods")
def list_payment_methods():
    settings_keys = ("payment_telebirr", "payment_cbe")
    try:
        rows = supabase_request(
            "GET",
            "app_settings?select=key,value&key=in.(payment_telebirr,payment_cbe)",
        )
    except SupabaseError as exc:
        raise HTTPException(status_code=503, detail="Could not load payment details.") from exc

    settings = {row["key"]: row.get("value") for row in rows}
    methods = {}
    for method, key in zip(("TeleBirr", "CBE Birr"), settings_keys):
        value = settings.get(key)
        account_name = value.get("account_name", "") if isinstance(value, dict) else ""
        account_number = value.get("account_number", "") if isinstance(value, dict) else ""
        methods[method] = {
            "configured": bool(account_name and account_number),
            "account_name": account_name,
            "account_number": account_number,
        }
    return methods


@app.get("/api/profile")
def get_profile(x_telegram_init_data: str | None = Header(default=None)):
    user = telegram_user(x_telegram_init_data)
    user_id = f"tg_{user['id']}"
    try:
        rows = supabase_request(
            "GET",
            "user_profiles?select=full_name,phone_number,winnings_balance"
            f"&user_id=eq.{user_id}&limit=1",
        )
    except SupabaseError as exc:
        raise HTTPException(status_code=503, detail="Could not load wallet profile.") from exc

    if not rows:
        return {
            "full_name": " ".join(
                part for part in (user.get("first_name"), user.get("last_name")) if part
            ),
            "phone_number": None,
            "main_balance": 0.00,
        }

    profile = rows[0]
    return {
        "full_name": profile.get("full_name") or "",
        "phone_number": profile.get("phone_number"),
        "main_balance": float(profile.get("winnings_balance") or 0),
    }


@app.post("/api/deposits", status_code=201)
def create_deposit(
    payload: DepositRequest,
    x_telegram_init_data: str | None = Header(default=None),
):
    user = telegram_user(x_telegram_init_data)
    user_id = f"tg_{user['id']}"
    row = {
        "user_id": user_id,
        "telegram_user_id": user["id"],
        "user_name": " ".join(
            part for part in (user.get("first_name"), user.get("last_name")) if part
        )[:120],
        "amount": payload.amount,
        "payment_method": payload.payment_method,
        "payment_proof": payload.payment_proof,
        "status": "pending_review",
    }
    try:
        inserted = supabase_request(
            "POST",
            "wallet_deposit_requests",
            row,
            prefer="return=representation",
        )
    except SupabaseError as exc:
        if exc.status_code == 409:
            raise HTTPException(
                status_code=409,
                detail="You already have a deposit request awaiting review.",
            ) from exc
        raise HTTPException(status_code=503, detail="Could not save the deposit request.") from exc

    if not inserted:
        raise HTTPException(status_code=502, detail="The database did not confirm the request.")

    request_id = inserted[0]["id"]
    admin_text = (
        "New deposit request\n"
        f"Request: {request_id}\n"
        f"User: {row['user_name'] or user_id} ({user_id})\n"
        f"Amount: {payload.amount:.2f} ETB\n"
        f"Method: {payload.payment_method}\n"
        f"Proof: {payload.payment_proof}"
    )
    try:
        send_admin_message(admin_text, request_id)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Request {request_id} was saved, but admin notification failed. Contact support.",
        ) from exc

    return {"id": request_id, "status": "pending_review"}


@app.post("/api/coupons/redeem")
def redeem_coupon(
    payload: CouponRedemption,
    x_telegram_init_data: str | None = Header(default=None),
):
    user = telegram_user(x_telegram_init_data)
    code = payload.code.strip().upper()
    if not re.fullmatch(r"[A-Z0-9_-]{4,32}", code):
        raise HTTPException(status_code=422, detail="Enter a valid promo code.")

    try:
        rows = supabase_request(
            "GET",
            "app_settings?select=value&key=eq.active_coupon&limit=1",
        )
    except SupabaseError as exc:
        raise HTTPException(status_code=503, detail="Could not validate the promo code.") from exc

    active_coupon = rows[0].get("value") if rows else None
    if not isinstance(active_coupon, dict) or active_coupon.get("code") != code:
        raise HTTPException(status_code=400, detail="This promo code is invalid or inactive.")

    reward_amount = 40.00
    user_id = f"tg_{user['id']}"
    try:
        supabase_request(
            "POST",
            "wallet_coupon_redemptions",
            {
                "coupon_code": code,
                "user_id": user_id,
                "telegram_user_id": user["id"],
                "reward_amount": reward_amount,
            },
            prefer="return=minimal",
        )
    except SupabaseError as exc:
        if exc.status_code == 409:
            raise HTTPException(
                status_code=409,
                detail="You have already redeemed this promo code.",
            ) from exc
        raise HTTPException(status_code=503, detail="Could not record the promo-code redemption.") from exc

    return {
        "status": "redeemed",
        "reward_amount": reward_amount,
        "balance_note": "The reward is for the browser demo balance and is not withdrawable.",
    }


@app.get("/api/deposits")
def list_deposits(x_telegram_init_data: str | None = Header(default=None)):
    user = telegram_user(x_telegram_init_data)
    user_id = f"tg_{user['id']}"
    try:
        rows = supabase_request(
            "GET",
            "wallet_deposit_requests"
            f"?select=id,amount,payment_method,status,created_at"
            f"&user_id=eq.{user_id}&order=created_at.desc&limit=20",
        )
    except SupabaseError as exc:
        raise HTTPException(status_code=503, detail="Could not load deposit requests.") from exc
    return rows


@app.post("/api/profile/password")
def change_password(
    payload: PasswordChange,
    x_telegram_init_data: str | None = Header(default=None),
):
    user = telegram_user(x_telegram_init_data)
    user_id = f"tg_{user['id']}"
    try:
        profile = supabase_request(
            "GET",
            "user_profiles"
            f"?select=user_id,password_hash,phone_verified_at"
            f"&user_id=eq.{user_id}&limit=1",
        )
        if not profile:
            raise HTTPException(
                status_code=404,
                detail="Register and verify your phone with the Telegram bot before setting a password.",
            )
        if not profile[0].get("phone_verified_at"):
            raise HTTPException(
                status_code=403,
                detail="Verify your phone with the Telegram bot before setting a password.",
            )
        current_hash = profile[0].get("password_hash")
        if current_hash and not verify_password(payload.current_password, current_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect.")
        supabase_request(
            "PATCH",
            f"user_profiles?user_id=eq.{user_id}",
            {"password_hash": hash_password(payload.new_password)},
            prefer="return=minimal",
        )
    except SupabaseError as exc:
        raise HTTPException(status_code=503, detail="Could not update the password.") from exc
    return {"status": "updated"}
