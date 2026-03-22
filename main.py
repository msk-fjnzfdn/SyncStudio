from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.wsgi import WSGIMiddleware
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base, joinedload
from sqlalchemy import select
from contextlib import asynccontextmanager

from database import User, Room, PersonRoom, init_db
from auth_utils import decode_token
from flask_auth import flask_app

ASYNC_DATABASE_URL = "sqlite+aiosqlite:///./app.db"

async_engine = create_async_engine(ASYNC_DATABASE_URL, connect_args={"check_same_thread": False})
AsyncSessionLocal = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as db:
        yield db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Room API", version="3.0.0", lifespan=lifespan)


async def current_user(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Нет токена")
    payload = decode_token(authorization[7:])
    if not payload:
        raise HTTPException(401, "Невалидный токен")
    result = await db.execute(select(User).filter(User.id == int(payload["sub"])))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    return user


class RoomCreate(BaseModel):
    name: str
    max_members: int = 10

class RoomUpdate(BaseModel):
    name: Optional[str] = None
    max_members: Optional[int] = None

class AddUser(BaseModel):
    user_id: int

class FileUpdate(BaseModel):
    file: str



@app.get("/rooms", tags=["Rooms"])
async def list_rooms(db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    result = await db.execute(select(Room).options(joinedload(Room.members)))
    rooms = result.unique().scalars().all()
    return [
        {"id": r.id, "name": r.name, "max_members": r.max_members, "members_count": len(r.members)}
        for r in rooms
    ]


@app.post("/rooms", tags=["Rooms"], status_code=201)
async def create_room(body: RoomCreate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    room = Room(name=body.name, max_members=body.max_members)
    db.add(room)
    await db.commit()
    await db.refresh(room)
    db.add(PersonRoom(user_id=user.id, room_id=room.id))
    await db.commit()
    return {"id": room.id, "name": room.name, "max_members": room.max_members}


@app.get("/rooms/{room_id}", tags=["Rooms"])
async def get_room(room_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    result = await db.execute(
        select(Room)
        .options(joinedload(Room.members).joinedload(PersonRoom.user))
        .filter(Room.id == room_id)
    )
    room = result.unique().scalar_one_or_none()
    if not room:
        raise HTTPException(404, "Комната не найдена")
    return {
        "id": room.id, "name": room.name, "max_members": room.max_members,
        "members": [
            {"user_id": pr.user.id, "login": pr.user.login, "name": pr.user.name, "has_file": pr.file is not None}
            for pr in room.members
        ],
    }


@app.patch("/rooms/{room_id}", tags=["Rooms"])
async def update_room(room_id: int, body: RoomUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    result = await db.execute(select(Room).filter(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(404, "Комната не найдена")
    if body.name:
        room.name = body.name
    if body.max_members:
        room.max_members = body.max_members
    await db.commit()
    return {"message": "Обновлено", "id": room.id}


@app.delete("/rooms/{room_id}", tags=["Rooms"])
async def delete_room(room_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    result = await db.execute(select(Room).filter(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(404, "Комната не найдена")
    await db.execute(select(PersonRoom).filter(PersonRoom.room_id == room_id))
    await db.delete(room)
    await db.commit()
    return {"message": "Комната удалена"}


@app.post("/rooms/{room_id}/members", tags=["Members"])
async def add_user(room_id: int, body: AddUser, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    result = await db.execute(select(Room).filter(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(404, "Комната не найдена")
    if len(room.members) >= room.max_members:
        raise HTTPException(400, "Комната заполнена")
    result = await db.execute(select(User).filter(User.id == body.user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(404, "Пользователь не найден")
    result = await db.execute(select(PersonRoom).filter(PersonRoom.user_id == body.user_id, PersonRoom.room_id == room_id))
    if result.scalar_one_or_none():
        raise HTTPException(409, "Пользователь уже в комнате")
    db.add(PersonRoom(user_id=body.user_id, room_id=room_id))
    await db.commit()
    return {"message": f"{target.login} добавлен в комнату {room.name}"}


@app.delete("/rooms/{room_id}/members/{user_id}", tags=["Members"])
async def remove_user(room_id: int, user_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    result = await db.execute(select(PersonRoom).filter(PersonRoom.user_id == user_id, PersonRoom.room_id == room_id))
    pr = result.scalar_one_or_none()
    if not pr:
        raise HTTPException(404, "Пользователь не в этой комнате")
    await db.delete(pr)
    await db.commit()
    return {"message": "Пользователь удалён из комнаты"}


@app.put("/rooms/{room_id}/file", tags=["Files"])
async def save_file(room_id: int, body: FileUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    result = await db.execute(select(PersonRoom).filter(PersonRoom.user_id == user.id, PersonRoom.room_id == room_id))
    pr = result.scalar_one_or_none()
    if not pr:
        raise HTTPException(403, "Вы не состоите в этой комнате")
    pr.file = body.file
    await db.commit()
    return {"message": "Файл сохранён"}


@app.get("/rooms/{room_id}/file", tags=["Files"])
async def get_my_file(room_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    result = await db.execute(select(PersonRoom).filter(PersonRoom.user_id == user.id, PersonRoom.room_id == room_id))
    pr = result.scalar_one_or_none()
    if not pr:
        raise HTTPException(403, "Вы не состоите в этой комнате")
    return {"file": pr.file}


@app.get("/rooms/{room_id}/files", tags=["Files"])
async def get_all_files(room_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    result = await db.execute(select(Room).filter(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(404, "Комната не найдена")
    result = await db.execute(select(PersonRoom).filter(PersonRoom.room_id == room_id, PersonRoom.file.isnot(None)))
    members = result.scalars().all()
    return [{"user_id": pr.user_id, "file": pr.file} for pr in members]


@app.delete("/rooms/{room_id}/file", tags=["Files"])
async def delete_file(room_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    result = await db.execute(select(PersonRoom).filter(PersonRoom.user_id == user.id, PersonRoom.room_id == room_id))
    pr = result.scalar_one_or_none()
    if not pr:
        raise HTTPException(403, "Вы не состоите в этой комнате")
    pr.file = None
    await db.commit()
    return {"message": "Файл удалён"}


app.mount("/", WSGIMiddleware(flask_app))