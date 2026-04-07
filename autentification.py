import httpx
from fastapi import APIRouter, HTTPException
from fastapi import Cookie
from fastapi.responses import RedirectResponse, JSONResponse

from const import YANDEX_TOKEN_URL, YANDEX_AUTH_URL, YANDEX_USER_INFO_URL, REDIRECT_URI, CLIENT_SECRET, CLIENT_ID
from database import get_conn, queries
from jwt_utils import create_access_token, create_refresh_token, decode_jwt

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login():
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(f"{YANDEX_AUTH_URL}?{query}")


@router.get("/callback")
async def callback(code: str):
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            YANDEX_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if token_response.status_code != 200:
        raise HTTPException(status_code=400, detail="Ошибка получения токена")

    token_data = token_response.json()
    access_token = token_data["access_token"]

    async with httpx.AsyncClient() as client:
        user_response = await client.get(
            YANDEX_USER_INFO_URL,
            headers={"Authorization": f"OAuth {access_token}"},
            params={"format": "json"},
        )

    if user_response.status_code != 200:
        raise HTTPException(status_code=400, detail="Ошибка получения данных пользователя")

    user_info = user_response.json()
    print(user_info)

    async with get_conn() as conn:
        user = await queries.get_user_by_yandex_id(conn, yandex_id=user_info["id"])

        if not user:
            user = await queries.create_user(
                conn,
                email=user_info["default_email"],
                username=user_info["real_name"],
                role_id=3,
                yandex_id=user_info["id"],
            )

    access_token = create_access_token(user["id"])
    refresh_token = create_refresh_token(user["id"])

    response = RedirectResponse(url="/dashboard")
    response.set_cookie("access_token", access_token, httponly=True, max_age=900)
    response.set_cookie("refresh_token", refresh_token, httponly=True, max_age=2592000)
    return response


@router.post("/refresh")
async def refresh(refresh_token: str = Cookie(None)):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Нет refresh токена")

    try:
        payload = decode_jwt(refresh_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Невалидный refresh токен")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Неверный тип токена")

    access_token = create_access_token(int(payload["sub"]))

    response = JSONResponse({"ok": True})
    response.set_cookie("access_token", access_token, httponly=True, max_age=900)
    return response
