import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import WebSocket

from .config import settings
from .models import ChatMessage, ChatUser
from .services.chat_history_service import ChatHistoryStore, InMemoryChatHistoryStore

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from uuid import uuid4


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}
        self.active_users: dict[str, ChatUser] = {}
        self.registered_users: dict[str, ChatUser] = {}
        self.history_store: ChatHistoryStore = InMemoryChatHistoryStore()
        self.revoked_tokens: dict[str, int] = {}
        self.read_receipts: dict[str, list[dict]] = {}
        self._expiry_tasks: dict[str, asyncio.Task] = {}

    def set_history_store(self, store: ChatHistoryStore) -> None:
        self.history_store = store

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
            payload = jwt.decode(
                token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
            )
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
            payload = jwt.decode(
                token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
            )
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
        for existing in self.registered_users.values():
            if existing.nickname == normalized:
                return existing, self.create_token(existing.id)
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        user = ChatUser(id=user_id, nickname=normalized, joined_at=now, is_online=False)
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
        self.history_store.save_group_message(msg)

    def save_dm_message(self, msg: ChatMessage) -> None:
        self.history_store.save_dm_message(msg)

    def get_group_messages(self, limit: int = 50) -> list[ChatMessage]:
        return self.history_store.get_group_messages(limit)

    def get_dm_history(self, user_a: str, user_b: str, limit: int = 50) -> list[ChatMessage]:
        return self.history_store.get_dm_history(user_a, user_b, limit)

    # ── Consultas ─────────────────────────────────────────────────────────────

    def get_online_users(self) -> list[ChatUser]:
        return list(self.active_users.values())

    def get_user(self, user_id: str) -> Optional[ChatUser]:
        return self.registered_users.get(user_id)

    def update_public_key(self, user_id: str, public_key: str) -> bool:
        user = self.registered_users.get(user_id)
        if not user:
            return False
        user.public_key = public_key
        return True

    # ── Vistos (read receipts) ────────────────────────────────────────────────

    def get_message_by_id(self, message_id: str) -> Optional[ChatMessage]:
        return self.history_store.get_message_by_id(message_id)

    def record_read(self, message_id: str, reader_id: str) -> Optional[dict]:
        msg = self.get_message_by_id(message_id)
        if not msg or not msg.allow_read_receipt:
            return None
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
        if msg.ttl is None:
            return
        task = asyncio.create_task(self._expire_message(msg))
        self._expiry_tasks[msg.id] = task

    async def _expire_message(self, msg: ChatMessage) -> None:
        if msg.ttl is None:
            return
        await asyncio.sleep(float(msg.ttl))
        expired_payload = {"type": "message_expired", "message_id": msg.id}
        self.history_store.delete_message(msg)
        if msg.type == "group":
            await self.broadcast(expired_payload)
        elif msg.type == "dm" and msg.recipient_id:
            await self.send_to(msg.sender_id, expired_payload)
            await self.send_to(msg.recipient_id, expired_payload)
        self.read_receipts.pop(msg.id, None)
        self._expiry_tasks.pop(msg.id, None)
