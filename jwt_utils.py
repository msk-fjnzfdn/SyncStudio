from jose import jwt
import datetime

from const import ACCESS_TOKEN_EXPIRE_HOURS, ALGORITHM, SECRET_KEY




def create_access_token(user_id: int) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": str(user_id),
        "exp": now + datetime.timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS),
        "iat": now,
        "type": "access"
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_jwt(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def create_refresh_token(user_id: int) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": now + datetime.timedelta(days=30),
        "iat": now,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)