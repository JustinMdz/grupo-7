"""
Rutas de persistencia con Firebase - Grupo 2.

Endpoints exclusivos para el almacenamiento persistente en Firebase.

POST /api/firebase/messages          — Guardar mensaje (group o dm)
GET  /api/firebase/messages          — Historial grupal desde Firebase
GET  /api/firebase/messages/dm/{other_id} — Historial DM desde Firebase
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request

from ..config import settings
from ..models import ChatMessage, CreateMessageRequest

router = APIRouter(prefix="/api/firebase", tags=["firebase"])


def get_manager(request: Request):
    return request.app.state.manager


def get_history_store(request: Request):
    return request.app.state.history_store


def _current_user_id(request: Request) -> str:
    """Extrae y valida el user_id del token JWT"""
    manager = get_manager(request)
    auth = request.headers.get("Authorization", "")

    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "MISSING_OR_INVALID_AUTH",
                "message": "Debes enviar Authorization: Bearer <token>.",
            },
        )

    token = auth.split(" ", 1)[1]
    current_user_id = manager.decode_token(token)
    if not current_user_id or not manager.get_user(current_user_id):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "INVALID_TOKEN",
                "message": "Token inválido o usuario no registrado.",
            },
        )
    return current_user_id


def _parse_ttl(ttl: int | None) -> int | None:
    """Valida TTL entre 1 segundo y 86400 segundos (1 día)"""
    if ttl is None:
        return None
    if 1 <= ttl <= 86400:
        return ttl
    raise HTTPException(
        status_code=400,
        detail={
            "code": "INVALID_TTL",
            "message": "ttl debe ser un entero entre 1 y 86400 segundos.",
        },
    )


@router.post("/messages", response_model=ChatMessage)
def create_message(body: CreateMessageRequest, request: Request) -> ChatMessage:
    """
    Crea y persiste un mensaje en Firebase.

    - **type**: "group" o "dm"
    - **content**: texto del mensaje (1-1000 caracteres)
    - **recipient_id**: requerido si type es "dm"
    - **ttl**: segundos hasta expirar (1-86400, opcional)
    - **allow_read_receipt**: notificar lectura (default: true)
    """
    manager = get_manager(request)
    current_user_id = _current_user_id(request)
    current_user = manager.get_user(current_user_id)
    history_store = get_history_store(request)

    # Validar contenido
    content = body.content.strip()
    if not content:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "EMPTY_CONTENT",
                "message": "El mensaje no puede estar vacío.",
            },
        )

    if len(content) > 1000:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "MESSAGE_TOO_LONG",
                "message": "El mensaje es demasiado largo (máx 1000 caracteres).",
            },
        )

    # Validar TTL
    ttl = _parse_ttl(body.ttl)
    expires_at = None
    if ttl is not None:
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat()

    # Validar si es DM
    if body.type == "dm":
        if not body.recipient_id:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "MISSING_RECIPIENT",
                    "message": "recipient_id es requerido para mensajes DM.",
                },
            )
        if body.recipient_id == current_user_id:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "SELF_DM",
                    "message": "No puedes enviarte un DM a ti mismo.",
                },
            )
        if not manager.get_user(body.recipient_id):
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "RECIPIENT_NOT_FOUND",
                    "message": "El destinatario no existe.",
                },
            )

    # Crear mensaje
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

    # Persistir en Firebase
    if body.type == "group":
        history_store.save_group_message(message)
    else:
        history_store.save_dm_message(message)

    return message


@router.get("/messages", response_model=list[ChatMessage])
def get_group_messages(request: Request, limit: int = 50) -> list[ChatMessage]:
    """
    Recupera historial grupal desde Firebase.

    - **limit**: máximo 100 mensajes (default: 50)
    """
    if not settings.firebase_enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "FIREBASE_DISABLED",
                "message": "Firebase no está habilitado.",
            },
        )

    limit = min(limit, 100)
    history_store = get_history_store(request)
    return history_store.get_group_messages(limit)


@router.get("/messages/dm/{other_id}", response_model=list[ChatMessage])
def get_dm_history(
    other_id: str, request: Request, limit: int = 50
) -> list[ChatMessage]:
    """
    Recupera historial DM desde Firebase entre el usuario autenticado y otro.

    - **other_id**: user_id del otro participante
    - **limit**: máximo 100 mensajes (default: 50)
    """
    if not settings.firebase_enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "FIREBASE_DISABLED",
                "message": "Firebase no está habilitado.",
            },
        )

    manager = get_manager(request)
    current_user_id = _current_user_id(request)
    limit = min(limit, 100)
    history_store = get_history_store(request)

    return history_store.get_dm_history(current_user_id, other_id, limit)
