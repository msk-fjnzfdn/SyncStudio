from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Text, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

DATABASE_URL = "sqlite:///./app.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class UserType(Base):
    __tablename__ = "user_types"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)

    users = relationship("User", back_populates="user_type")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    surname = Column(String)
    name = Column(String)
    login = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    type_id = Column(Integer, ForeignKey("user_types.id"), default=1)

    user_type = relationship("UserType", back_populates="users")
    rooms = relationship("PersonRoom", back_populates="user")


class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    max_members = Column(Integer, default=10)

    members = relationship("PersonRoom", back_populates="room")


class PersonRoom(Base):
    __tablename__ = "person_room"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    file = Column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("user_id", "room_id", name="uq_user_room"),)

    user = relationship("User", back_populates="rooms")
    room = relationship("Room", back_populates="members")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    if not db.query(UserType).first():
        db.add_all([
            UserType(name="user"),
            UserType(name="admin"),
            UserType(name="moderator"),
        ])
        db.commit()
    db.close()