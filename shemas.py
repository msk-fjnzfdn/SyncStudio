from pydantic import BaseModel

class RoomCreate(BaseModel):
    name: str
    max_members: int

class AddFileToRoom(BaseModel):
    room_id: int