from fastapi import WebSocket
from typing import Dict, Optional, Set

class RoomManager:
    def __init__(self):
        # room_id → {
        #   "teacher_ws": WebSocket | None,
        #   "students": dict[student_id, {"ws": WebSocket, "code": str, "lang": str}],
        #   "teacher_code": str,
        #   "teacher_viewing": student_id | None  ← какого ученика смотрит учитель
        # }
        self.rooms: Dict[str, dict] = {}

    def get_or_create(self, room_id: str) -> dict:
        if room_id not in self.rooms:
            self.rooms[room_id] = {
                "teacher_ws": None,
                "students": {},
                "teacher_code": "",
                "teacher_viewing": None,
            }
        return self.rooms[room_id]

    # ── подключение ──────────────────────────────────────────────

    async def connect_teacher(self, room_id: str, ws: WebSocket):
        await ws.accept()
        self.get_or_create(room_id)["teacher_ws"] = ws

    async def connect_student(self, room_id: str, student_id: str, ws: WebSocket):
        await ws.accept()
        room = self.get_or_create(room_id)
        room["students"][student_id] = {"ws": ws, "code": "", "lang": "python"}
        # Отдаём актуальный код учителя сразу при входе
        if room["teacher_code"]:
            await ws.send_json({
                "type": "teacher_code_broadcast",
                "code": room["teacher_code"],
            })

    def disconnect_teacher(self, room_id: str):
        room = self.rooms.get(room_id)
        if room:
            room["teacher_ws"] = None
            room["teacher_viewing"] = None

    def disconnect_student(self, room_id: str, student_id: str):
        room = self.rooms.get(room_id)
        if not room:
            return
        room["students"].pop(student_id, None)
        if room["teacher_viewing"] == student_id:
            room["teacher_viewing"] = None

    # ── обработка сообщений ──────────────────────────────────────

    async def handle_teacher_message(self, room_id: str, data: dict):
        room = self.rooms.get(room_id)
        if not room:
            return
        msg_type = data.get("type")

        if msg_type == "code_update":
            # Учитель обновил свой код → транслируем всем ученикам
            room["teacher_code"] = data.get("code", "")
            await self._broadcast_to_students(room, {
                "type": "teacher_code_broadcast",
                "code": room["teacher_code"],
                "lang": data.get("lang", "python"),
            })

        elif msg_type == "view_student":
            # Учитель хочет смотреть код конкретного ученика
            student_id = data.get("student_id")
            room["teacher_viewing"] = student_id
            student = room["students"].get(student_id)
            teacher_ws = room["teacher_ws"]
            if student and teacher_ws:
                await teacher_ws.send_json({
                    "type": "student_code_snapshot",
                    "student_id": student_id,
                    "code": student["code"],
                    "lang": student["lang"],
                })

        elif msg_type == "edit_student":
            # Учитель отредактировал код ученика
            student_id = data.get("student_id")
            new_code = data.get("code", "")
            student = room["students"].get(student_id)
            if student:
                student["code"] = new_code
                # Уведомляем самого ученика что его код изменён
                try:
                    await student["ws"].send_json({
                        "type": "teacher_edit",
                        "code": new_code,
                        "lang": student["lang"],
                    })
                except Exception:
                    pass

        elif msg_type == "stop_viewing":
            room["teacher_viewing"] = None

    async def handle_student_message(self, room_id: str, student_id: str, data: dict):
        room = self.rooms.get(room_id)
        if not room:
            return

        if data.get("type") == "code_update":
            student = room["students"].get(student_id)
            if not student:
                return
            student["code"] = data.get("code", "")
            student["lang"] = data.get("lang", "python")

            # Если учитель сейчас смотрит именно этого ученика — шлём live
            if room["teacher_viewing"] == student_id and room["teacher_ws"]:
                try:
                    await room["teacher_ws"].send_json({
                        "type": "student_code_snapshot",
                        "student_id": student_id,
                        "code": student["code"],
                        "lang": student["lang"],
                        "live": True,
                    })
                except Exception:
                    pass

    # ── helpers ──────────────────────────────────────────────────

    async def _broadcast_to_students(self, room: dict, message: dict):
        dead = []
        for sid, student in room["students"].items():
            try:
                await student["ws"].send_json(message)
            except Exception:
                dead.append(sid)
        for sid in dead:
            room["students"].pop(sid, None)