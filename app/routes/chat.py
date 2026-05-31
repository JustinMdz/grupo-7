"""
Rutas HTTP del chat.

POST /api/chat/join          — Registrar un nickname y obtener token
POST /api/chat/logout        — Revocar el token actual
POST /api/chat/messages      — Guardar mensaje (group o dm)
GET  /api/chat/users         — Usuarios conectados ahora
GET  /api/chat/messages      — Historial del chat grupal
GET  /api/chat/messages/dm/{other_id} — Historial de DMs entre dos usuarios
PUT  /api/chat/users/me/public-key    — Registrar llave pública Curve25519
GET  /health                 — Healthcheck
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request

from ..models import (
    ChatMessage,
    ChatUser,
    CreateMessageRequest,
    JoinRequest,
    JoinResponse,
    PublicKeyRequest,
)

router = APIRouter()


def get_manager(request: Request):
    return request.app.state.manager


def _current_user_id(request: Request) -> str:
    manager = get_manager(request)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"code": "MISSING_OR_INVALID_AUTH", "message": "Debes enviar Authorization: Bearer <token>."},
        )
    token = auth.split(" ", 1)[1]
    user_id = manager.decode_token(token)
    if not user_id or not manager.get_user(user_id):
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": "Token inválido o usuario no registrado."},
        )
    return user_id


def _parse_ttl(ttl: int | None) -> int | None:
    if ttl is None:
        return None
    if 1 <= ttl <= 86400:
        return ttl
    raise HTTPException(
        status_code=400,
        detail={"code": "INVALID_TTL", "message": "ttl debe ser un entero entre 1 y 86400."},
    )


@router.get("/health")
def healthcheck() -> dict:
    return {"status": "ok", "service": "chat-backend"}


@router.post("/api/chat/join", response_model=JoinResponse)
def join_chat(body: JoinRequest, request: Request) -> dict:
    nickname = body.nickname.strip()
    if not nickname:
        raise HTTPException(status_code=400, detail={"code": "EMPTY_NICKNAME", "message": "El nickname no puede estar vacío."})
    if len(nickname) > 30:
        raise HTTPException(status_code=400, detail={"code": "NICKNAME_TOO_LONG", "message": "El nickname no puede superar 30 caracteres."})
    manager = get_manager(request)
    user, token = manager.register_user(nickname)
    return {"user": user, "token": token}


@router.post("/api/chat/logout")
def logout(request: Request) -> dict:
    manager = get_manager(request)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"code": "MISSING_OR_INVALID_AUTH", "message": "Debes enviar Authorization: Bearer <token>."})
    token = auth.split(" ", 1)[1]
    if not manager.revoke_token(token):
        raise HTTPException(status_code=401, detail={"code": "INVALID_TOKEN", "message": "Token inválido o ya expirado."})
    return {"status": "ok", "message": "Sesión cerrada."}


@router.get("/api/chat/users", response_model=list[ChatUser])
def get_online_users(request: Request) -> list:
    manager = get_manager(request)
    return manager.get_online_users()


@router.get("/api/chat/messages", response_model=list[ChatMessage])
def get_group_messages(request: Request, limit: int = 50) -> list:
    limit = min(limit, 100)
    manager = get_manager(request)
    return manager.get_group_messages(limit)


@router.post("/api/chat/messages", response_model=ChatMessage)
def create_message(body: CreateMessageRequest, request: Request) -> ChatMessage:
    manager = get_manager(request)
    current_user_id = _current_user_id(request)
    current_user = manager.get_user(current_user_id)

    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail={"code": "EMPTY_CONTENT", "message": "El mensaje no puede estar vacío."})
    if len(content) > 1000:
        raise HTTPException(status_code=400, detail={"code": "MESSAGE_TOO_LONG", "message": "El mensaje es demasiado largo (máx 1000 caracteres)."})

    ttl = _parse_ttl(body.ttl)
    expires_at = None
    if ttl is not None:
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat()

    if body.type == "dm":
        if not body.recipient_id:
            raise HTTPException(status_code=400, detail={"code": "MISSING_RECIPIENT", "message": "recipient_id es requerido para mensajes DM."})
        if body.recipient_id == current_user_id:
            raise HTTPException(status_code=400, detail={"code": "SELF_DM", "message": "No puedes enviarte un DM a ti mismo."})
        if not manager.get_user(body.recipient_id):
            raise HTTPException(status_code=404, detail={"code": "RECIPIENT_NOT_FOUND", "message": "El destinatario no existe."})

    message = ChatMessage(
        id=str(uuid.uuid4()),
        sender_id=current_user_id,
        sender_nickname=current_user.nickname,
        content=content,
        type=body.type,
        recipient_id=body.recipient_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        ttl=ttl,
        expires_at=expires_at,
        allow_read_receipt=body.allow_read_receipt,
    )

    if body.type == "group":
        manager.save_group_message(message)
    else:
        manager.save_dm_message(message)

    return message


@router.get("/api/chat/messages/dm/{other_id}", response_model=list[ChatMessage])
def get_dm_history(other_id: str, request: Request) -> list:
    manager = get_manager(request)
    current_user_id = _current_user_id(request)
    return manager.get_dm_history(current_user_id, other_id)


@router.put("/api/chat/users/me/public-key", status_code=200)
def register_public_key(body: PublicKeyRequest, request: Request) -> dict:
    manager = get_manager(request)
    user_id = _current_user_id(request)
    if not manager.update_public_key(user_id, body.public_key):
        raise HTTPException(status_code=404, detail={"code": "USER_NOT_FOUND", "message": "Usuario no encontrado."})
    return {"status": "ok"}
