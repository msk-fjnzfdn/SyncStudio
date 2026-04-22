from fastapi import WebSocket
from typing import Dict, Optional, Set


class RoomManager:
    def __init__(self):
        # room_id → {
        #   "teacher_ws": WebSocket | None,
        #   "students": dict[student_id, {"ws": WebSocket, "code": str, "lang": str}],
        #   "teacher_code": str,
        #   "teacher_viewing": student_id | None
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
        room = self.get_or_create(room_id)
        room["teacher_ws"] = ws

        # При подключении учителя сразу отправляем ему список всех, кто уже в комнате
        for student_id in room["students"]:
            await ws.send_json({
                "type": "student_joined",
                "student_id": student_id
            })

    async def connect_student(self, room_id: str, student_id: str, ws: WebSocket):
        await ws.accept()
        room = self.get_or_create(room_id)
        room["students"][student_id] = {"ws": ws, "code": "", "lang": "python", "output": ""}

        # 1. Отдаём код учителя ученику
        if room["teacher_code"]:
            await ws.send_json({
                "type": "teacher_code_broadcast",
                "code": room["teacher_code"],
            })

        # 2. Уведомляем учителя о новом ученике
        if room["teacher_ws"]:
            await room["teacher_ws"].send_json({
                "type": "student_joined",
                "student_id": student_id
            })

    def disconnect_teacher(self, room_id: str):
        room = self.rooms.get(room_id)
        if room:
            room["teacher_ws"] = None
            room["teacher_viewing"] = None

    async def disconnect_student(self, room_id: str, student_id: str):
        room = self.rooms.get(room_id)
        print(room)
        if not room:
            return

        room["students"].pop(student_id, None)

        if room["teacher_viewing"] == student_id:
            room["teacher_viewing"] = None

        # Уведомляем учителя, что ученик ушел
        if room["teacher_ws"]:
            try:
                await room["teacher_ws"].send_json({
                    "type": "student_left",
                    "student_id": student_id
                })
            except Exception:
                pass

    # ── обработка сообщений ──────────────────────────────────────

    async def handle_teacher_message(self, room_id: str, data: dict):
        room = self.rooms.get(room_id)
        if not room:
            return
        msg_type = data.get("type")

        if msg_type == "code_update":
            room["teacher_code"] = data.get("code", "")
            await self._broadcast_to_students(room, {
                "type": "teacher_code_broadcast",
                "code": room["teacher_code"],
                "lang": data.get("lang", "python"),
            })

        elif msg_type == "view_student":
            student_id = data.get("student_id")
            # Уведомляем предыдущего просматриваемого ученика — разблокировать
            prev_id = room.get("teacher_viewing")
            if prev_id and prev_id != student_id:
                prev_student = room["students"].get(prev_id)
                if prev_student:
                    try:
                        await prev_student["ws"].send_json({"type": "viewing_stop"})
                    except Exception:
                        pass

            room["teacher_viewing"] = student_id
            student = room["students"].get(student_id)
            teacher_ws = room["teacher_ws"]
            if student and teacher_ws:
                # Уведомляем ученика — заблокировать редактор
                try:
                    await student["ws"].send_json({"type": "viewing_start"})
                except Exception:
                    pass
                await teacher_ws.send_json({
                    "type": "student_code_snapshot",
                    "student_id": student_id,
                    "code": student["code"],
                    "lang": student["lang"],
                    "output": student.get("output", ""),
                })

        elif msg_type == "edit_student":
            student_id = data.get("student_id")
            new_code = data.get("code", "")
            student = room["students"].get(student_id)
            if student:
                student["code"] = new_code
                try:
                    await student["ws"].send_json({
                        "type": "teacher_edit",
                        "code": new_code,
                        "lang": student["lang"],
                    })
                except Exception:
                    pass

        elif msg_type == "stop_viewing":
            prev_id = room.get("teacher_viewing")
            if prev_id:
                prev_student = room["students"].get(prev_id)
                if prev_student:
                    try:
                        await prev_student["ws"].send_json({"type": "viewing_stop"})
                    except Exception:
                        pass
            room["teacher_viewing"] = None

    async def handle_student_message(self, room_id: str, student_id: str, data: dict):
        room = self.rooms.get(room_id)
        if not room:
            return

        student = room["students"].get(student_id)
        if not student:
            return

        if data.get("type") == "code_update":
            student["code"] = data.get("code", "")
            student["lang"] = data.get("lang", "python")

            if room["teacher_viewing"] == student_id and room["teacher_ws"]:
                try:
                    await room["teacher_ws"].send_json({
                        "type": "student_code_snapshot",
                        "student_id": student_id,
                        "code": student["code"],
                        "lang": student["lang"],
                        "output": student.get("output", ""),
                        "live": True,
                    })
                except Exception:
                    pass

        elif data.get("type") == "console_output":
            student["output"] = data.get("output", "")
            student["output_success"] = data.get("success", True)

            if room["teacher_viewing"] == student_id and room["teacher_ws"]:
                try:
                    await room["teacher_ws"].send_json({
                        "type": "student_console_output",
                        "student_id": student_id,
                        "output": student["output"],
                        "success": student["output_success"],
                    })
                except Exception:
                    pass

    async def _broadcast_to_students(self, room: dict, message: dict):
        dead = []
        for sid, student in room["students"].items():
            try:
                await student["ws"].send_json(message)
            except Exception:
                dead.append(sid)
        for sid in dead:
            room["students"].pop(sid, None)