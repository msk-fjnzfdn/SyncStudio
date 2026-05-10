import shutil
from typing import Optional
import pathlib

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Path
from fastapi.responses import FileResponse

from dependencies import get_current_user
from database import get_conn, queries
from shemas import RoomCreate, AddFileToRoom

router = APIRouter(prefix="/room", tags=["room"])


@router.post("/create", status_code=status.HTTP_201_CREATED)
async def create_room(room_data: RoomCreate, user_id: int = Depends(get_current_user)):
    async with get_conn() as conn:
        if (await queries.is_user_staff(conn, user_id=user_id))[0]:
            room = await queries.create_room(
                conn,
                name=room_data.name,
                max_members=room_data.max_members,
                created_by=user_id
            )

            room_user = await queries.add_user_to_room(
                conn,
                room_id=room['id'],
                user_id=user_id
            )

            if not room:
                raise HTTPException(status_code=500, detail="Не удалось создать комнату")

            if not room_user:
                raise HTTPException(
                    status_code=500,
                    detail="Не удалось создать связь между юсером и комнатой"
                )

            return {'ok': True, 'room_id': room['id'], 'room_name': room['name']}

        raise HTTPException(403, "У вас нет прав на создание комнаты")


@router.get('/', status_code=status.HTTP_200_OK)
async def get_rooms(user_id: int = Depends(get_current_user)):
    async with get_conn() as conn:
        rooms = await queries.get_all_room_user_id(conn, user_id=user_id)

        return {'ok': True, 'rooms': rooms}


@router.patch('/add_file', status_code=status.HTTP_200_OK)
async def add_file(
        room_id: int,
        user_id: int = Depends(get_current_user),
        target_user_id: Optional[int] = None,  # учитель передаёт id ученика
        image: Optional[UploadFile] = File(None)
):
    if not image:
        return {"error": "Файл не загружен"}

    # Определяем от чьего имени сохраняем
    async with get_conn() as conn:
        role = (await queries.is_user_staff(conn, user_id=user_id))[0]

    if target_user_id and target_user_id != user_id:
        # Только учитель может сохранять чужой файл
        if not role:
            raise HTTPException(status_code=403, detail="Нет прав сохранять файл другого пользователя")
        save_as_user_id = target_user_id
    else:
        save_as_user_id = user_id

    content = await image.read()
    if len(content) > 5 * 1024 * 1024:
        return {"error": "Файл слишком большой"}

    upload_path = pathlib.Path(f"uploads/room_{room_id}")
    upload_path.mkdir(parents=True, exist_ok=True)
    file_location = upload_path / f'user_{save_as_user_id}'

    with open(file_location, "wb") as buffer:
        buffer.write(content)

    async with get_conn() as conn:
        queries.add_file_to_room(conn, path_to_file=str(file_location), user_id=save_as_user_id, room_id=room_id)

    return {"info": f"Файл сохранен как {file_location}"}


@router.put("/add_user_to_room/{room_id}", status_code=status.HTTP_201_CREATED)
async def add_user_to_room(
        room_id: int,
        username: str,
        user_id: int = Depends(get_current_user),
):
    async with get_conn() as conn:
        if not (await queries.is_user_staff(conn, user_id=user_id))[0]:
            raise HTTPException(403, "Нет прав")

        room = await queries.get_room_by_id(conn, room_id=room_id)
        if not room:
            raise HTTPException(404, "Комната не найдена")

        target = await queries.get_user_by_username(conn, username=username)
        if not target:
            raise HTTPException(404, f"Пользователь '{username}' не найден")

        result = await queries.add_user_to_room(
            conn,
            room_id=room_id,
            user_id=target["id"],
        )
        if not result:
            raise HTTPException(409, "Пользователь уже в комнате")

        return {"ok": True, "user_id": target["id"], "username": target["username"]}


@router.patch("/settings/{room_id}", status_code=status.HTTP_200_OK)
async def update_room_settings(
        room_id: int,
        room_data: RoomCreate,
        user_id: int = Depends(get_current_user),
):
    async with get_conn() as conn:
        if not (await queries.is_user_staff(conn, user_id=user_id))[0]:
            raise HTTPException(403, "Нет прав")

        room = await queries.get_room_by_id(conn, room_id=room_id)
        if not room:
            raise HTTPException(404, "Комната не найдена")

        if room["created_by"] != user_id:
            raise HTTPException(403, "Только создатель может изменять комнату")

        updated = await queries.update_room_data(
            conn,
            name=room_data.name,
            max_members=room_data.max_members,
            room_id=room_id,
        )
        return {"ok": True, "room": dict(updated)}


@router.delete("/{room_id}", status_code=status.HTTP_200_OK)
async def delete_room(
        room_id: int,
        user_id: int = Depends(get_current_user),
):
    async with get_conn() as conn:
        if not (await queries.is_user_staff(conn, user_id=user_id))[0]:
            raise HTTPException(403, "Нет прав")

        room = await queries.get_room_by_id(conn, room_id=room_id)
        if not room:
            raise HTTPException(404, "Комната не найдена")

        if room["created_by"] != user_id:
            raise HTTPException(403, "Только создатель может удалять комнату")

        await queries.delete_room_by_id(conn, id=room_id)
        return {"ok": True}


@router.get("/settings/{room_id}", status_code=status.HTTP_200_OK)
async def get_room_settings(
        room_id: int,
        user_id: int = Depends(get_current_user),
):
    async with get_conn() as conn:
        if not (await queries.is_user_staff(conn, user_id=user_id))[0]:
            raise HTTPException(403, "Нет прав")

        members = await queries.get_room_members(conn, room_id=room_id)
        if not members:
            raise HTTPException(404, "Комната не найдена")

        first = members[0]
        return {
            "ok": True,
            "room": {
                "id": room_id,
                "max_members": first["max_members"],
                "current_members": first["current_members"],
                "created_at": first["room_created_at"],
            },
            "members": [
                {
                    "id": m["id"],
                    "username": m["username"],
                    "email": m["email"],
                    "joined_at": m["joined_at"],
                }
                for m in members
            ],
        }


@router.get('/get_file', status_code=status.HTTP_200_OK)
async def get_file(
        room_id: int,
        user_id: int = Depends(get_current_user)
):
    file_location = pathlib.Path(f"uploads/room_{room_id}") / f'user_{user_id}'

    if not file_location.exists():
        raise HTTPException(status_code=404, detail="Файл не найден")

    return FileResponse(path=file_location, filename=f'user_{user_id}')
