from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, Cookie, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from contextlib import asynccontextmanager
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exception_handlers import http_exception_handler
import asyncpg

from database import init_pool, close_pool, get_conn, queries
from starlette.middleware.wsgi import WSGIMiddleware
from autentification import flask_app
import room
from room_manager import RoomManager
from dependencies import get_current_user
from jwt_utils import decode_jwt


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(lifespan=lifespan)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

app.mount("/auth", WSGIMiddleware(flask_app))
app.mount("/admin", WSGIMiddleware(flask_app))
app.include_router(room.router)


# ── Page routes ───────────────────────────────────────────────


@app.exception_handler(404)
async def not_found_exception_handler(request: Request, exc):
    return templates.TemplateResponse(request, '404.html',{
        "request": request,
        "error_code": "404",
        "error_tag": "STATUS.NOT_FOUND",
        "error_title": "Путь не найден",
        "request_path": request.url.path,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "home_url": "/dashboard"
    }, status_code=404)

@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    return templates.TemplateResponse(request, '404.html', {
        "request": request,
        "error_code": "500",
        "error_tag": "CRITICAL_SERVER_ERR",
        "error_title": "Ошибка ядра",
        "error_description": "Произошел критический сбой на стороне сервера. Мы уже работаем над восстановлением доступа.",
        "debug_message": str(exc), # Только для режима разработки!
        "theme_color": "#e85555"
    }, status_code=500)

@app.exception_handler(401)
async def redirect_to_login(request: Request, exc):
    if request.url.path.startswith("/room") or request.url.path.startswith("/auth"):
        return JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized"}
        )
    return RedirectResponse('/')

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # Если уже залогинен — редирект на дашборд
    token = request.cookies.get("access_token")
    if token:
        try:
            decode_jwt(token)
            return RedirectResponse("/dashboard")
        except Exception:
            pass
    return templates.TemplateResponse(request, "login.html")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse("/")

    try:
        payload = decode_jwt(token)
        user_id = int(payload["sub"])
    except Exception:
        return RedirectResponse("/")

    async with get_conn() as conn:
        rooms = [
            row
            async for row in queries.get_rooms_info_by_user_id(conn, user_id=user_id)
        ]
        is_staff_row = await queries.is_user_staff(conn, user_id=user_id)
        is_admin_row = await queries.is_user_admin(conn, user_id=user_id)
        user_data = await queries.get_user_by_id(conn, id=user_id)

    is_staff = bool(is_staff_row[0] and is_staff_row["is_staff"])
    is_admin = bool(is_admin_row[0] and is_admin_row["is_superuser"])

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "rooms": rooms,
            "username": user_data["username"] if user_data else str(user_id),
            "is_staff": is_staff,
            "is_admin": is_admin,
        },
    )


@app.get("/admin")
async def admin(request: Request, user_id: int = Depends(get_current_user)):
    async with get_conn() as conn:
        is_admin = await queries.is_user_admin(conn, user_id=user_id)

    if not is_admin[0]:
        raise HTTPException(status_code=404, detail='Такой страницы не существует')

    return templates.TemplateResponse(
        request,
        "admin.html",
        {'request': request, 'is_admin': True}
    )

@app.get("/all_users")
async def users(request: Request, user_id: int = Depends(get_current_user)):
    async with get_conn() as conn:
        is_admin = await queries.is_user_admin(conn, user_id=user_id)
        if not is_admin[0]:
            raise HTTPException(status_code=404, detail='Такой страницы не существует')

        all_users_gen = queries.get_all_users(conn)
        all_users = [u async for u in all_users_gen]
    return all_users


@app.patch("/change_user_role")
async def change_user_role(request: Request, target: int, role: str, user_id: int = Depends(get_current_user)):
    async with get_conn() as conn:
        if not (await queries.is_user_admin(conn, user_id=user_id))[0]:
            raise HTTPException(status_code=404, detail='Такой страницы не существует')
        try:
            async with conn.transaction():
                id = await queries.change_user_role(conn, user_id=target, role=role)
                if id == 'UPDATE 0':
                    raise HTTPException(status_code=500, detail='nternal server error')

            return {"status": "success"}
        except asyncpg.IntegrityConstraintViolationError:
            raise HTTPException(status_code=400, detail=f"Role '{role}' does not exist")
        except Exception as e:
            print(f"Database error: {e}")
            raise HTTPException(status_code=500, detail='Internal server error')



@app.delete("/delete_user")
async def delete_user(request: Request, target: int, user_id: int = Depends(get_current_user)):
    async with get_conn() as conn:
        is_admin = await queries.is_user_admin(conn, user_id=user_id)
        if not is_admin[0]:
            raise HTTPException(status_code=404, detail='Такой страницы не существует')

        try:
            async with conn.transaction():
                print(f"DEBUG: target value is {target} type {type(target)}")
                # await queries.delete_user(conn, target=target)
                await conn.execute('DELETE FROM "user" WHERE id = $1', target)
                await conn.execute('DELETE FROM room_user WHERE user_id = $1', target)
        except Exception as e:
            print(f"Database error: {e}")
            raise HTTPException(status_code=500, detail='Internal server error')



@app.get("/room/{room_id}", response_class=HTMLResponse)
async def room_page(request: Request, room_id: int):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse("/")

    try:
        payload = decode_jwt(token)
        user_id = int(payload["sub"])
    except Exception:
        return RedirectResponse("/")

    async with get_conn() as conn:
        is_staff_row = await queries.is_user_staff(conn, user_id=user_id)
        room_data = await queries.get_room_by_id(conn, room_id=room_id)
        user_data = await queries.get_user_by_id(conn, id=user_id)
        is_admin = (await queries.is_user_admin(conn, user_id=user_id))[0]

    if not room_data:
        return RedirectResponse("/dashboard")

    is_staff = bool(is_staff_row[0] and is_staff_row["is_staff"])
    role = "teacher" if is_staff else "student"

    return templates.TemplateResponse(
        request,
        "room.html",
        {
            "request": request,
            "room_id": room_id,
            "room_name": room_data["name"] if room_data else str(room_id),
            "role": role,
            "user_id": user_id,
            "username": user_data["username"] if user_data else str(user_id),
            'is_admin': is_admin
        },
    )


@app.get("/auth/logout")
async def logout():
    response = RedirectResponse("/")
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return response


# ── WebSocket ─────────────────────────────────────────────────

manager = RoomManager()


@app.websocket("/ws/{room_id}/teacher")
async def teacher_endpoint(websocket: WebSocket, room_id: str):
    await manager.connect_teacher(room_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await manager.handle_teacher_message(room_id, data)
    except WebSocketDisconnect:
        manager.disconnect_teacher(room_id)


@app.websocket("/ws/{room_id}/student/{student_id}")
async def student_endpoint(websocket: WebSocket, room_id: str, student_id: str):
    await manager.connect_student(room_id, student_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await manager.handle_student_message(room_id, student_id, data)
    except WebSocketDisconnect:
        await manager.disconnect_student(room_id, student_id)


@app.get("/room/{room_id}/settings", response_class=HTMLResponse)
async def room_settings_page(request: Request, room_id: int):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse("/")
    try:
        payload = decode_jwt(token)
        user_id = int(payload["sub"])
    except Exception:
        return RedirectResponse("/")

    async with get_conn() as conn:
        is_staff_row = await queries.is_user_staff(conn, user_id=user_id)
        if not (is_staff_row[0] and is_staff_row["is_staff"]):
            return RedirectResponse("/dashboard")
        room = await queries.get_room_by_id(conn, room_id=room_id)
        if not room:
            return RedirectResponse("/dashboard")

    return templates.TemplateResponse(
        request,
        "room_settings.html",
        {
            "room_id": room_id,
            "room": dict(room),
        },
    )

