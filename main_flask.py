from flask import Flask, render_template, request, redirect, session, jsonify
from functools import wraps
from flask_sock import Sock
import json
from contextlib import asynccontextmanager

from database import init_pool, close_pool, get_conn, queries
import autentification
import room
from room_manager import RoomManager
from dependencies import get_current_user
from jwt_utils import decode_jwt

@asynccontextmanager
async def lifespan(app: Flask):
    await init_pool()
    yield
    await close_pool()

app = Flask(__name__)
sock = Sock(app)

app.register_blueprint(autentification.router)
app.register_blueprint(room.router)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = get_current_user()
        if not user_id:
            return redirect("/")
        return f(*args, **kwargs)
    return decorated_function



@app.route("/")
def index():
    token = session.get("access_token")
    if token:
        try:
            decode_jwt(token)
            return redirect("/dashboard")
        except Exception:
            pass
    return render_template("login.html")

@app.route("/dashboard")
@login_required
def dashboard():
    user_id = get_current_user()
    
    async def fetch_data():
        async with get_conn() as conn:
            rooms = [row async for row in queries.get_rooms_info_by_user_id(conn, user_id=user_id)]
            is_staff_row = await queries.is_user_staff(conn, user_id=user_id)
            is_admin_row = await queries.is_user_admin(conn, user_id=user_id)
            return rooms, is_staff_row, is_admin_row
    
    rooms, is_staff_row, is_admin_row = run_async(fetch_data())
    is_staff = bool(is_staff_row and is_staff_row["is_staff"])
    is_admin = bool(is_admin_row and is_admin_row["is_superuser"])
    
    return render_template("dashboard.html", 
                          rooms=rooms, 
                          is_staff=is_staff, 
                          is_admin=is_admin)

@app.route("/room/<int:room_id>")
@login_required
def room_page(room_id):
    user_id = get_current_user()
    
    async def fetch_data():
        async with get_conn() as conn:
            is_staff_row = await queries.is_user_staff(conn, user_id=user_id)
            room_data = await queries.get_room_by_id(conn, room_id=room_id)
            return is_staff_row, room_data
    
    is_staff_row, room_data = run_async(fetch_data())
    
    if not room_data:
        return redirect("/dashboard")
    
    is_staff = bool(is_staff_row and is_staff_row["is_staff"])
    role = "teacher" if is_staff else "student"
    
    return render_template("room.html", 
                          room_id=room_id, 
                          role=role, 
                          user_id=user_id)

@app.route("/auth/logout")
def logout():
    session.pop("access_token", None)
    session.pop("refresh_token", None)
    return redirect("/")

manager = RoomManager()

@sock.route("/ws/<room_id>/teacher")
def teacher_endpoint(ws, room_id):
    async def handle():
        await manager.connect_teacher(room_id, ws)
        try:
            while True:
                data = ws.receive()
                if data is None:
                    break
                await manager.handle_teacher_message(room_id, json.loads(data))
        except Exception:
            manager.disconnect_teacher(room_id)
    
    run_async(handle())

@sock.route("/ws/<room_id>/student/<student_id>")
def student_endpoint(ws, room_id, student_id):
    async def handle():
        await manager.connect_student(room_id, student_id, ws)
        try:
            while True:
                data = ws.receive()
                if data is None:
                    break
                await manager.handle_student_message(room_id, student_id, json.loads(data))
        except Exception:
            manager.disconnect_student(room_id, student_id)
    
    run_async(handle())

@app.route("/room/<int:room_id>/settings")
@login_required
def room_settings_page(room_id):
    user_id = get_current_user()
    
    async def fetch_data():
        async with get_conn() as conn:
            is_staff_row = await queries.is_user_staff(conn, user_id=user_id)
            if not (is_staff_row and is_staff_row["is_staff"]):
                return None
            room_data = await queries.get_room_by_id(conn, room_id=room_id)
            return room_data
    
    room_data = run_async(fetch_data())
    if not room_data:
        return redirect("/dashboard")
    
    return render_template("room_settings.html", 
                          room_id=room_id, 
                          room=dict(room_data))