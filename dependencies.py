from fastapi import Cookie, HTTPException, Depends
from jwt_utils import decode_jwt


async def get_current_user(access_token: str = Cookie(None)) -> int:
    if not access_token:
        raise HTTPException(status_code=401, detail="Не авторизован")

    try:
        payload = decode_jwt(access_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Невалидный токен")

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Неверный тип токена")

    return int(payload["sub"])

