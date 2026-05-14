"""
Аутентификация и админка на Flask.

Подключение в main.py:
    from autentification import flask_app
    from starlette.middleware.wsgi import WSGIMiddleware
    app.mount("/auth", WSGIMiddleware(flask_app))
    app.mount("/admin", WSGIMiddleware(flask_app))

    # router из этого файла больше не нужен — убери:
    #   app.include_router(autentification.router)
"""

import httpx
import asyncio
import asyncpg
from functools import wraps

from flask import Flask, Blueprint, request, redirect, render_template, jsonify, make_response

from const import (
    YANDEX_TOKEN_URL, YANDEX_AUTH_URL, YANDEX_USER_INFO_URL,
    REDIRECT_URI, CLIENT_SECRET, CLIENT_ID,
)
from database import queries, pool
from jwt_utils import create_access_token, create_refresh_token, decode_jwt


# ── asyncio helper (Flask синхронный, pool асинхронный) ───────

def run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


async def _with_conn(coro_fn):
    """Берёт соединение из общего пула FastAPI и возвращает обратно."""
    conn = await pool.acquire()
    try:
        return await coro_fn(conn)
    finally:
        await pool.release(conn)


# ── Декораторы ────────────────────────────────────────────────

def _get_user_id_from_cookie():
    token = request.cookies.get("access_token")
    if not token:
        return None, "no_token"
    try:
        payload = decode_jwt(token)
    except Exception:
        return None, "invalid"
    if payload.get("type") != "access":
        return None, "wrong_type"
    return int(payload["sub"]), None


def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user_id, err = _get_user_id_from_cookie()
        if err:
            return redirect("/")
        return f(*args, user_id=user_id, **kwargs)
    return wrapper


def require_auth_json(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user_id, err = _get_user_id_from_cookie()
        if err:
            return jsonify({"detail": "Unauthorized"}), 401
        return f(*args, user_id=user_id, **kwargs)
    return wrapper


def require_admin(f):
    @wraps(f)
    def wrapper(*args, user_id, **kwargs):
        is_admin_row = run(_with_conn(
            lambda conn: queries.is_user_admin(conn, user_id=user_id)
        ))
        if not (is_admin_row and is_admin_row[0]):
            return jsonify({"detail": "Такой страницы не существует"}), 404
        return f(*args, user_id=user_id, **kwargs)
    return wrapper


# ── Auth Blueprint (/auth) ────────────────────────────────────

auth_bp = Blueprint("auth", __name__)


@auth_bp.get("/login")
def login():
    params = "&".join([
        "response_type=code",
        f"client_id={CLIENT_ID}",
        f"redirect_uri={REDIRECT_URI}",
    ])
    return redirect(f"{YANDEX_AUTH_URL}?{params}")


@auth_bp.get("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return jsonify({"detail": "Отсутствует code"}), 400

    token_resp = httpx.post(
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
    if token_resp.status_code != 200:
        return jsonify({"detail": "Ошибка получения токена"}), 400

    yandex_token = token_resp.json()["access_token"]

    user_resp = httpx.get(
        YANDEX_USER_INFO_URL,
        headers={"Authorization": f"OAuth {yandex_token}"},
        params={"format": "json"},
    )
    if user_resp.status_code != 200:
        return jsonify({"detail": "Ошибка получения данных пользователя"}), 400

    user_info = user_resp.json()

    async def _get_or_create(conn):
        user = await queries.get_user_by_yandex_id(conn, yandex_id=user_info["id"])
        if not user:
            user = await queries.create_user(
                conn,
                email=user_info["default_email"],
                username=user_info["real_name"],
                role_id=3,
                yandex_id=user_info["id"],
            )
        return user

    user = run(_with_conn(_get_or_create))

    access_token = create_access_token(user["id"])
    refresh_token = create_refresh_token(user["id"])

    resp = make_response(redirect("/dashboard"))
    resp.set_cookie("access_token", access_token, httponly=True, max_age=900)
    resp.set_cookie("refresh_token", refresh_token, httponly=True, max_age=2592000)
    return resp


@auth_bp.post("/refresh")
def refresh():
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        return jsonify({"detail": "Отсутствует сессионный ключ"}), 401

    try:
        payload = decode_jwt(refresh_token)
    except Exception:
        return jsonify({"detail": "Сессия истекла"}), 401

    if payload.get("type") != "refresh":
        return jsonify({"detail": "Некорректный тип авторизации"}), 401

    user_id = int(payload["sub"])
    new_access = create_access_token(user_id)
    new_refresh = create_refresh_token(user_id)

    resp = make_response(jsonify({"ok": True}))
    resp.set_cookie("access_token", new_access, httponly=True, max_age=900, samesite="Lax")
    resp.set_cookie("refresh_token", new_refresh, httponly=True, max_age=2592000, samesite="Lax")
    return resp


@auth_bp.get("/logout")
def logout():
    resp = make_response(redirect("/"))
    resp.delete_cookie("access_token")
    resp.delete_cookie("refresh_token")
    return resp


# ── Admin Blueprint (/admin) ──────────────────────────────────

admin_bp = Blueprint("admin", __name__)


@admin_bp.get("/")
@require_auth
@require_admin
def admin_page(user_id: int):
    return render_template("admin.html", is_admin=True)


@admin_bp.get("/all_users")
@require_auth_json
@require_admin
def all_users(user_id: int):
    users = run(_with_conn(
        lambda conn: _collect(queries.get_all_users(conn))
    ))
    return jsonify([dict(u) for u in users])


async def _collect(async_gen):
    return [u async for u in async_gen]


@admin_bp.patch("/change_user_role")
@require_auth_json
@require_admin
def change_user_role(user_id: int):
    target = request.args.get("target", type=int)
    role = request.args.get("role") or (request.json or {}).get("role")
    if not target or not role:
        return jsonify({"detail": "target and role are required"}), 400

    async def _change(conn):
        async with conn.transaction():
            result = await queries.change_user_role(conn, user_id=target, role=role)
            if result == "UPDATE 0":
                raise RuntimeError("no rows updated")

    try:
        run(_with_conn(_change))
        return jsonify({"status": "success"})
    except asyncpg.IntegrityConstraintViolationError:
        return jsonify({"detail": f"Role '{role}' does not exist"}), 400
    except Exception as e:
        print(f"Database error: {e}")
        return jsonify({"detail": "Internal server error"}), 500


@admin_bp.delete("/delete_user")
@require_auth_json
@require_admin
def delete_user(user_id: int):
    target = request.args.get("target", type=int)
    if not target:
        return jsonify({"detail": "target is required"}), 400

    async def _delete(conn):
        async with conn.transaction():
            await conn.execute('DELETE FROM "user" WHERE id = $1', target)
            await conn.execute('DELETE FROM room_user WHERE user_id = $1', target)

    try:
        run(_with_conn(_delete))
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"Database error: {e}")
        return jsonify({"detail": "Internal server error"}), 500


# ── Flask app ─────────────────────────────────────────────────

flask_app = Flask(__name__)
flask_app.register_blueprint(auth_bp, url_prefix="/auth")
flask_app.register_blueprint(admin_bp, url_prefix="/admin")
