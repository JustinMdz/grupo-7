

import asyncio
import base64
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import WebSocket

from .config import settings
from .models import ChatMessage, ChatUser

#Imports para JWT
import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from datetime import datetime, timedelta
from uuid import uuid4

from .services.chat_history_service import ChatHistoryStore

class ConnectionManager:
    def __init__(self, history_store: ChatHistoryStore | None = None) -> None:
        # WebSockets activos: user_id → WebSocket
        self.active_connections: dict[str, WebSocket] = {}

        # Usuarios conectados ahora: user_id → ChatUser
        self.active_users: dict[str, ChatUser] = {}

        # Todos los usuarios que alguna vez hicieron /join: user_id → ChatUser
        # (se limpian al reiniciar el servidor)
        self.registered_users: dict[str, ChatUser] = {}

        # Historial del chat grupal (últimos MAX_GROUP_MESSAGES mensajes)
        self.group_messages: list[ChatMessage] = []

        # Historial de DMs: frozenset({uid_a, uid_b}) → lista de mensajes
        self.dm_history: dict[frozenset, list[ChatMessage]] = {}

        # Tokens revocados: jti → exp (timestamp Unix)
        self.revoked_tokens: dict[str, int] = {}
        # Vistos: message_id → lista de {"user_id": ..., "seen_at": ...}
        self.read_receipts: dict[str, list[dict]] = {}

        # Tareas de expiración pendientes: message_id → asyncio.Task
        self._expiry_tasks: dict[str, asyncio.Task] = {}

        # Persistencia compartida: memoria, Firebase o composición de ambas.
        self.history_store = history_store

    # ── Tokens ───────────────────────────────────────────────────────────────

    def create_token(self, user_id: str) -> str:
        now = datetime.utcnow()
        exp = now + timedelta(seconds=settings.jwt_exp_seconds)
        payload = {"sub": user_id, "iat": now, "exp": exp, "jti": str(uuid4())}
        return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    def _cleanup_revoked_tokens(self) -> None:
        now_ts = int(datetime.now(timezone.utc).timestamp())
        self.revoked_tokens = {
            jti: exp for jti, exp in self.revoked_tokens.items() if exp > now_ts
        }

    def decode_token(self, token: str) -> Optional[str]:
        try:    
            payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
            jti = payload.get("jti")
            if not jti:
                return None

            self._cleanup_revoked_tokens()
            if str(jti) in self.revoked_tokens:
                return None

            return payload.get("sub")
        except ExpiredSignatureError:
            return None
        except InvalidTokenError:
            return None

    def revoke_token(self, token: str) -> bool:
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        except InvalidTokenError:
            return False

        jti = payload.get("jti")
        exp = payload.get("exp")
        if not jti or not exp:
            return False

        self.revoked_tokens[str(jti)] = int(exp)
        self._cleanup_revoked_tokens()
        return True

    # ── Registro ─────────────────────────────────────────────────────────────

    def register_user(self, nickname: str) -> tuple[ChatUser, str]:
    
        normalized = nickname.strip()

        # Retornar usuario existente si el nickname ya está registrado
        for existing in self.registered_users.values():
            if existing.nickname == normalized:
                return existing, self.create_token(existing.id)

        # Crear nuevo usuario
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        user = ChatUser(
            id=user_id,
            nickname=normalized,
            joined_at=now,
            is_online=False,
        )

        self.registered_users[user_id] = user
        token = self.create_token(user_id)
        return user, token

    # ── Ciclo de vida WebSocket ───────────────────────────────────────────────

    async def connect(self, websocket: WebSocket, user_id: str) -> bool:
        
        user = self.registered_users.get(user_id)
        if not user:
            return False

        await websocket.accept()
        user.is_online = True
        self.active_connections[user_id] = websocket
        self.active_users[user_id] = user
        return True

    async def disconnect(self, user_id: str) -> None:
       
        self.active_connections.pop(user_id, None)
        user = self.active_users.pop(user_id, None)
        if user:
            user.is_online = False

    # ── Envío de mensajes ─────────────────────────────────────────────────────

    async def broadcast(self, message: dict, exclude_id: Optional[str] = None) -> None:
       
        for uid, ws in list(self.active_connections.items()):
            if uid != exclude_id:
                try:
                    await ws.send_json(message)
                except Exception:
                    # Si falla el envío, ignoramos — el disconnect se detectará
                    # en el próximo receive del loop principal
                    pass

    async def send_to(self, user_id: str, message: dict) -> None:
       
        ws = self.active_connections.get(user_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                pass

    # ── Historial ─────────────────────────────────────────────────────────────

    def save_group_message(self, msg: ChatMessage) -> None:
        if self.history_store is not None:
            self.history_store.save_group_message(msg)
            return

        self.group_messages.append(msg)
        # Mantener solo los últimos N mensajes
        if len(self.group_messages) > settings.max_group_messages:
            self.group_messages = self.group_messages[-settings.max_group_messages:]

    def save_dm_message(self, msg: ChatMessage) -> None:
        if self.history_store is not None:
            self.history_store.save_dm_message(msg)
            return

        if not msg.recipient_id:
            return
        key = frozenset({msg.sender_id, msg.recipient_id})
        history = self.dm_history.setdefault(key, [])
        history.append(msg)
        if len(history) > settings.max_dm_messages:
            self.dm_history[key] = history[-settings.max_dm_messages:]

    def get_group_messages(self, limit: int = 50) -> list[ChatMessage]:
        if self.history_store is not None:
            return self.history_store.get_group_messages(limit)

        return self.group_messages[-limit:]

    def get_dm_history(
        self, user_a: str, user_b: str, limit: int = 50
    ) -> list[ChatMessage]:
        if self.history_store is not None:
            return self.history_store.get_dm_history(user_a, user_b, limit)

        key = frozenset({user_a, user_b})
        return self.dm_history.get(key, [])[-limit:]

    # ── Consultas ─────────────────────────────────────────────────────────────

    def get_online_users(self) -> list[ChatUser]:
        return list(self.active_users.values())

    def get_user(self, user_id: str) -> Optional[ChatUser]:
        return self.registered_users.get(user_id)

    # ── Vistos (read receipts) ────────────────────────────────────────────────

    def get_message_by_id(self, message_id: str) -> Optional[ChatMessage]:
        if self.history_store is not None:
            return self.history_store.get_message_by_id(message_id)

        for msg in self.group_messages:
            if msg.id == message_id:
                return msg
        for history in self.dm_history.values():
            for msg in history:
                if msg.id == message_id:
                    return msg
        return None

    def record_read(self, message_id: str, reader_id: str) -> Optional[dict]:
        """
        Registra que reader_id leyó el mensaje.
        Retorna {"seen_by": ..., "seen_at": ..., "sender_id": ...} si procede,
        o None si el mensaje no existe, no permite receipt, o ya fue registrado.
        """
        msg = self.get_message_by_id(message_id)
        if not msg or not msg.allow_read_receipt:
            return None
        # El remitente no se marca como lector de su propio mensaje
        if msg.sender_id == reader_id:
            return None
        receipts = self.read_receipts.setdefault(message_id, [])
        if any(r["user_id"] == reader_id for r in receipts):
            return None
        seen_at = datetime.now(timezone.utc).isoformat()
        receipts.append({"user_id": reader_id, "seen_at": seen_at})
        return {"seen_by": reader_id, "seen_at": seen_at, "sender_id": msg.sender_id}

    # ── Mensajes temporales ───────────────────────────────────────────────────

    async def schedule_expiry(self, msg: ChatMessage) -> None:
        """Programa la expiración de un mensaje con TTL."""
        if msg.ttl is None:
            return
        task = asyncio.create_task(self._expire_message(msg))
        self._expiry_tasks[msg.id] = task

    async def _expire_message(self, msg: ChatMessage) -> None:
        await asyncio.sleep(msg.ttl)
        expired_payload = {"type": "message_expired", "message_id": msg.id}

        if msg.type == "group":
            self.group_messages = [m for m in self.group_messages if m.id != msg.id]
            await self.broadcast(expired_payload)
        elif msg.type == "dm" and msg.recipient_id:
            key = frozenset({msg.sender_id, msg.recipient_id})
            if key in self.dm_history:
                self.dm_history[key] = [m for m in self.dm_history[key] if m.id != msg.id]
            await self.send_to(msg.sender_id, expired_payload)
            await self.send_to(msg.recipient_id, expired_payload)

        self.read_receipts.pop(msg.id, None)
        self._expiry_tasks.pop(msg.id, None)

    def delete_message(self, msg: ChatMessage) -> None:
        if self.history_store is not None:
            self.history_store.delete_message(msg)
            return

        if msg.type == "group":
            self.group_messages = [m for m in self.group_messages if m.id != msg.id]
            return

        if msg.recipient_id:
            key = frozenset({msg.sender_id, msg.recipient_id})
            if key in self.dm_history:
                self.dm_history[key] = [m for m in self.dm_history[key] if m.id != msg.id]
