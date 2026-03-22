from flask import Flask, request, jsonify
from database import SessionLocal, User, UserType, init_db
from auth_utils import hash_password, verify_password, create_token

flask_app = Flask(__name__)


def get_db():
    return SessionLocal()


@flask_app.route("/auth/register", methods=["POST"])
def register():
    data = request.get_json()

    required = ["email", "login", "password", "name", "surname"]
    if not all(k in data for k in required):
        return jsonify({"error": "Не все поля заполнены"}), 400

    db = get_db()
    try:
        if db.query(User).filter(User.email == data["email"]).first():
            return jsonify({"error": "Email уже занят"}), 409
        if db.query(User).filter(User.login == data["login"]).first():
            return jsonify({"error": "Логин уже занят"}), 409

        user = User(
            email=data["email"],
            login=data["login"],
            password=hash_password(data["password"]),
            name=data["name"],
            surname=data["surname"],
            type_id=1,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        token = create_token({"sub": str(user.id), "login": user.login})
        return jsonify({
            "message": "Пользователь зарегистрирован",
            "token": token,
            "user": {
                "id": user.id,
                "login": user.login,
                "email": user.email,
                "name": user.name,
                "surname": user.surname,
            }
        }), 201
    finally:
        db.close()


@flask_app.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json()

    if not data or "login" not in data or "password" not in data:
        return jsonify({"error": "Укажите логин и пароль"}), 400

    db = get_db()
    try:
        user = db.query(User).filter(User.login == data["login"]).first()
        if not user or not verify_password(data["password"], user.password):
            return jsonify({"error": "Неверный логин или пароль"}), 401

        token = create_token({"sub": str(user.id), "login": user.login})
        return jsonify({
            "message": "Успешный вход",
            "token": token,
            "user": {
                "id": user.id,
                "login": user.login,
                "email": user.email,
                "name": user.name,
                "surname": user.surname,
                "type": user.user_type.name if user.user_type else "user",
            }
        })
    finally:
        db.close()


@flask_app.route("/auth/me", methods=["GET"])
def me():
    """Проверка токена и получение своего профиля"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"error": "Нет токена"}), 401

    from auth_utils import decode_token
    payload = decode_token(auth[7:])
    if not payload:
        return jsonify({"error": "Невалидный токен"}), 401

    db = get_db()
    try:
        user = db.query(User).filter(User.id == int(payload["sub"])).first()
        if not user:
            return jsonify({"error": "Пользователь не найден"}), 404
        return jsonify({
            "id": user.id,
            "login": user.login,
            "email": user.email,
            "name": user.name,
            "surname": user.surname,
            "type": user.user_type.name if user.user_type else "user",
        })
    finally:
        db.close()
