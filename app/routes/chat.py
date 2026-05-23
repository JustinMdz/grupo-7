"""
Rutas HTTP del chat.

POST /api/chat/join          — Registrar un nickname y obtener token
GET  /api/chat/users         — Usuarios conectados ahora
GET  /api/chat/messages      — Historial del chat grupal
GET  /api/chat/messages/dm/{other_id} — Historial de DMs entre dos usuarios
GET  /health                 — Healthcheck
"""

from fastapi import APIRouter, HTTPException, Request

from ..models import ChatMessage, ChatUser, JoinRequest, JoinResponse

router = APIRouter()


def get_manager(request: Request):
    """Helper para obtener el ConnectionManager desde el estado de la app."""
    return request.app.state.manager


@router.get("/health")
def healthcheck() -> dict:
    return {"status": "ok", "service": "chat-backend"}


@router.post("/api/chat/join", response_model=JoinResponse)
def join_chat(body: JoinRequest, request: Request) -> dict:
    """
    Registra al usuario con solo un nickname.
    Devuelve un user_id y un token para conectarse al WebSocket.

    El token es simplemente el user_id en base64 — sin expiración ni firma.
    Cualquier alumno puede extender esto con JWT si lo desea.
    """
    nickname = body.nickname.strip()

    if not nickname:
        raise HTTPException(
            status_code=400,
            detail={"code": "EMPTY_NICKNAME", "message": "El nickname no puede estar vacío."},
        )

    if len(nickname) > 30:
        raise HTTPException(
            status_code=400,
            detail={"code": "NICKNAME_TOO_LONG", "message": "El nickname no puede superar 30 caracteres."},
        )

    manager = get_manager(request)
    user, token = manager.register_user(nickname)

    return {"user": user, "token": token}


@router.get("/api/chat/users", response_model=list[ChatUser])
def get_online_users(request: Request) -> list:
    """Devuelve la lista de usuarios conectados en este momento."""
    manager = get_manager(request)
    return manager.get_online_users()


@router.get("/api/chat/messages", response_model=list[ChatMessage])
def get_group_messages(request: Request, limit: int = 50) -> list:
    """
    Devuelve los últimos mensajes del chat grupal.
    Máximo 100.
    """
    limit = min(limit, 100)
    manager = get_manager(request)
    return manager.get_group_messages(limit)


@router.get("/api/chat/messages/dm/{other_id}", response_model=list[ChatMessage])
def get_dm_history(other_id: str, request: Request) -> list:
    """
    Devuelve el historial de DMs entre el usuario actual y other_id.

    Requiere el header X-User-Token para identificar quién hace la petición.
    """
    token = request.headers.get("X-User-Token")
    if not token:
        raise HTTPException(
            status_code=401,
            detail={"code": "MISSING_TOKEN", "message": "Falta el header X-User-Token."},
        )

    manager = get_manager(request)
    current_user_id = manager.decode_token(token)

    if not current_user_id or not manager.get_user(current_user_id):
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": "Token inválido o usuario no registrado."},
        )

    return manager.get_dm_history(current_user_id, other_id)
