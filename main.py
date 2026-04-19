from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, Cookie
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from flask import Flask
from a2wsgi import WSGIMiddleware
from contextlib import asynccontextmanager

from database import init_pool, close_pool, get_conn, queries
import autentification
import room
from room_manager import RoomManager
from dependencies import get_current_user
from jwt_utils import decode_jwt


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()

flask_app = Flask(__name__)
app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/flask", WSGIMiddleware(flask_app))

app.include_router(autentification.router)
app.include_router(room.router)


# ── Page routes ───────────────────────────────────────────────

@flask_app.route("/flask")
def flask_main():
    return "Hello World from Flask"

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
        rooms = [row async for row in queries.get_rooms_info_by_user_id(conn, user_id=user_id)]
        is_staff_row  = await queries.is_user_staff(conn, user_id=user_id)
        is_admin_row  = await queries.is_user_admin(conn, user_id=user_id)

    is_staff = bool(is_staff_row and is_staff_row["is_staff"])
    is_admin = bool(is_admin_row and is_admin_row["is_superuser"])

    return templates.TemplateResponse(request, "dashboard.html", {
        "request":  request,
        "rooms":    rooms,
        "is_staff": is_staff,
        "is_admin": is_admin,
    })


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
        room_data    = await queries.get_room_by_id(conn, room_id=room_id)

    if not room_data:
        return RedirectResponse("/dashboard")

    is_staff = bool(is_staff_row and is_staff_row["is_staff"])
    role = "teacher" if is_staff else "student"

    return templates.TemplateResponse(request,"room.html", {
        "request": request,
        "room_id": room_id,
        "role":    role,
        "user_id": user_id,
    })


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
        manager.disconnect_student(room_id, student_id)


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
        if not (is_staff_row and is_staff_row["is_staff"]):
            return RedirectResponse("/dashboard")
        room = await queries.get_room_by_id(conn, room_id=room_id)
        if not room:
            return RedirectResponse("/dashboard")

    return templates.TemplateResponse(request, "room_settings.html", {
        "room_id": room_id,
        "room": dict(room),
    })