"""
Ruta WebSocket del chat.

WS /ws/{token}

Protocolo (todos los mensajes son JSON):

Cliente → Servidor:
  { "type": "group_message", "content": "...", "ttl": 30, "allow_read_receipt": true }
  { "type": "dm", "to": "<user_id>", "content": "...", "ttl": 60, "allow_read_receipt": false }
  { "type": "mark_read", "message_id": "<id>" }
  { "type": "typing" }                         — grupo (broadcast)
  { "type": "typing", "to": "<user_id>" }      — DM (solo al destinatario)
  { "type": "stop_typing" }
  { "type": "ping" }

  Campos opcionales:
    ttl              — segundos hasta que el mensaje expire y se elimine (omitir = permanente)
    allow_read_receipt — si false, nadie notifica al remitente cuando lee (default: true)

Servidor → Cliente:
  { "type": "group_message", "message": { ...ChatMessage } }
  { "type": "dm", "message": { ...ChatMessage } }
  { "type": "message_seen", "message_id": "...", "seen_by": "<user_id>", "seen_at": "..." }
  { "type": "message_expired", "message_id": "..." }
  { "type": "typing", "user_id": "...", "nickname": "..." }
  { "type": "stop_typing", "user_id": "..." }
  { "type": "user_joined", "user": { ...ChatUser } }
  { "type": "user_left", "user_id": "..." }
  { "type": "users_list", "users": [ ...ChatUser ] }
  { "type": "group_history", "messages": [ ...ChatMessage ] }
  { "type": "group_key", "key": "<base64_32_bytes>" }
  { "type": "pong" }
  { "type": "error", "message": "..." }
"""

import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

from ..connection_manager import ConnectionManager
from ..config import settings
from ..models import ChatMessage, MediaAttachment
from ..services.moderation_service import censor

from pydantic import ValidationError

router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ttl(value) -> int | None:
    """Valida y retorna el TTL en segundos (1–86400), o None si no aplica."""
    if value is None:
        return None
    try:
        ttl = int(value)
        if 1 <= ttl <= 86400:
            return ttl
    except (TypeError, ValueError):
        pass
    return None


def _expires_iso(ttl: int | None) -> str | None:
    if ttl is None:
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat()


def _parse_media(value) -> MediaAttachment | None:
    """Valida el payload de media"""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("media debe ser un objeto.")
    try:
        return MediaAttachment(**value)
    except ValidationError as e:
        raise ValueError(f"media inválido: {e.errors()[0]['msg']}")


async def _handle_message(
    manager: ConnectionManager,
    user_id: str,
    nickname: str,
    data: dict,
) -> None:

    msg_type = data.get("type")

    # ── Mensaje al chat grupal ────────────────────────────────────────────────
    if msg_type == "group_message":
        content = str(data.get("content", "")).strip()
        try:
            media = _parse_media(data.get("media"))
        except ValueError as e:
            await manager.send_to(user_id, {"type": "error", "message": str(e)})
            return
        
        content = censor(content)

        if not content and media is None:
            await manager.send_to(user_id, {"type": "error", "message": "El mensaje no puede estar vacío."})
            return

        if len(content) > 1000:
            await manager.send_to(user_id, {"type": "error", "message": "El mensaje es demasiado largo (máx 1000 caracteres)."})
            return

        raw_ttl = data.get("ttl")
        ttl = _parse_ttl(raw_ttl)
        if raw_ttl is not None and ttl is None:
            await manager.send_to(user_id, {"type": "error", "message": "ttl inválido: debe ser un entero entre 1 y 86400."})
            return
        raw_receipt = data.get("allow_read_receipt", True)
        if not isinstance(raw_receipt, bool):
            await manager.send_to(user_id, {"type": "error", "message": "allow_read_receipt debe ser un booleano (true/false)."})
            return
        allow_read_receipt = raw_receipt
        expires_at = _expires_iso(ttl)

        msg = ChatMessage(
            id=str(uuid.uuid4()),
            sender_id=user_id,
            sender_nickname=nickname,
            content=content,
            type="group",
            recipient_id=None,
            timestamp=_now_iso(),
            ttl=ttl,
            expires_at=expires_at,
            allow_read_receipt=allow_read_receipt,
            media=media,
        )
        manager.save_group_message(msg)
        await manager.broadcast({
            "type": "group_message",
            "message": msg.model_dump(),
        })
        await manager.schedule_expiry(msg)

    # ── Mensaje privado (DM) ──────────────────────────────────────────────────
    elif msg_type == "dm":
        to_id = str(data.get("to", "")).strip()
        content = str(data.get("content", "")).strip()
        
        try:
            media = _parse_media(data.get("media"))
        except ValueError as e:
            await manager.send_to(user_id, {"type": "error", "message": str(e)})
            return

        content = censor(content)

        if not to_id:
            await manager.send_to(user_id, {"type": "error", "message": "Debes especificar el destinatario ('to')."})
            return

        if to_id == user_id:
            await manager.send_to(user_id, {"type": "error", "message": "No puedes enviarte un DM a ti mismo."})
            return

        if not manager.get_user(to_id):
            await manager.send_to(user_id, {"type": "error", "message": "El destinatario no existe."})
            return

        if not content and media is None:
            await manager.send_to(user_id, {"type": "error", "message": "El mensaje no puede estar vacío."})
            return

        if len(content) > 1000:
            await manager.send_to(user_id, {"type": "error", "message": "El mensaje es demasiado largo (máx 1000 caracteres)."})
            return

        raw_ttl = data.get("ttl")
        ttl = _parse_ttl(raw_ttl)
        if raw_ttl is not None and ttl is None:
            await manager.send_to(user_id, {"type": "error", "message": "ttl inválido: debe ser un entero entre 1 y 86400."})
            return
        raw_receipt = data.get("allow_read_receipt", True)
        if not isinstance(raw_receipt, bool):
            await manager.send_to(user_id, {"type": "error", "message": "allow_read_receipt debe ser un booleano (true/false)."})
            return
        allow_read_receipt = raw_receipt
        expires_at = _expires_iso(ttl)

        msg = ChatMessage(
            id=str(uuid.uuid4()),
            sender_id=user_id,
            sender_nickname=nickname,
            content=content,
            type="dm",
            recipient_id=to_id,
            timestamp=_now_iso(),
            ttl=ttl,
            expires_at=expires_at,
            allow_read_receipt=allow_read_receipt,
            media=media,
        )
        manager.save_dm_message(msg)

        payload = {"type": "dm", "message": msg.model_dump()}
        await manager.send_to(to_id, payload)
        await manager.send_to(user_id, payload)
        await manager.schedule_expiry(msg)

    # ── Marcar mensaje como leído ─────────────────────────────────────────────
    elif msg_type == "mark_read":
        message_id = str(data.get("message_id", "")).strip()
        if not message_id:
            await manager.send_to(user_id, {"type": "error", "message": "Debes especificar 'message_id'."})
            return

        receipt = manager.record_read(message_id, user_id)
        if receipt:
            await manager.send_to(receipt["sender_id"], {
                "type": "message_seen",
                "message_id": message_id,
                "seen_by": receipt["seen_by"],
                "seen_at": receipt["seen_at"],
            })

    # ── Escribiendo ───────────────────────────────────────────────────────────
    elif msg_type == "typing":
        to_id = data.get("to")
        payload = {"type": "typing", "user_id": user_id, "nickname": nickname}
        if to_id:
            await manager.send_to(to_id, payload)
        else:
            await manager.broadcast(payload, exclude_id=user_id)

    elif msg_type == "stop_typing":
        payload = {"type": "stop_typing", "user_id": user_id}
        await manager.broadcast(payload, exclude_id=user_id)

    # ── Ping ──────────────────────────────────────────────────────────────────
    elif msg_type == "ping":
        await manager.send_to(user_id, {"type": "pong"})

    else:
        await manager.send_to(user_id, {"type": "error", "message": f"Tipo de mensaje desconocido: '{msg_type}'."})


@router.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str) -> None:

    manager: ConnectionManager = websocket.app.state.manager

    user_id = manager.decode_token(token)
    if not user_id or not manager.get_user(user_id):
        await websocket.close(code=4001, reason="Token inválido o usuario no registrado.")
        return

    connected = await manager.connect(websocket, user_id)
    if not connected:
        await websocket.close(code=4001, reason="No se pudo conectar.")
        return

    user = manager.active_users[user_id]
    nickname = user.nickname

    await manager.broadcast(
        {"type": "user_joined", "user": user.model_dump()},
        exclude_id=user_id,
    )

    await manager.send_to(user_id, {
        "type": "users_list",
        "users": [u.model_dump() for u in manager.get_online_users()],
    })
    await manager.send_to(user_id, {
        "type": "group_history",
        "messages": [m.model_dump() for m in manager.get_group_messages(50)],
    })
    await manager.send_to(user_id, {
        "type": "group_key",
        "key": settings.group_encryption_key,
    })

    try:
        while True:
            data = await websocket.receive_json()
            await _handle_message(manager, user_id, nickname, data)

    except WebSocketDisconnect:
        pass

    except Exception:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=1011, reason="Error interno del servidor.")

    finally:
        await manager.disconnect(user_id)
        await manager.broadcast({
            "type": "user_left",
            "user_id": user_id,
        })
