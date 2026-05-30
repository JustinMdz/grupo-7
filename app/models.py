from typing import Literal, Optional

from pydantic import BaseModel


class ChatUser(BaseModel):
    
    id: str
    nickname: str
    joined_at: str       # ISO 8601
    is_online: bool
    public_key: str | None = None  # Para encriptación futura (Grupo 4)


class ChatMessage(BaseModel):
    """Mensaje del chat — grupal o DM."""
    id: str
    sender_id: str
    sender_nickname: str
    content: str
    type: Literal["group", "dm"]
    recipient_id: Optional[str] = None   # Solo presente en DMs
    timestamp: str                        # ISO 8601
    ttl: Optional[int] = None            # Segundos hasta expirar (None = permanente)
    expires_at: Optional[str] = None     # ISO 8601 — calculado al crear el mensaje
    allow_read_receipt: bool = True      # Si False, no se notifica al remitente cuando leen


# ── Payloads HTTP ────────────────────────────────────────────────────────────

class JoinRequest(BaseModel):
    nickname: str


class JoinResponse(BaseModel):
    user: ChatUser
    token: str


class CreateMessageRequest(BaseModel):
    type: Literal["group", "dm"]
    content: str
    recipient_id: Optional[str] = None
    ttl: Optional[int] = None
    allow_read_receipt: bool = True


# ── Payloads WebSocket (cliente → servidor) ───────────────────────────────────

class WsGroupMessage(BaseModel):
    type: Literal["group_message"]
    content: str
    ttl: Optional[int] = None
    allow_read_receipt: bool = True


class WsDMMessage(BaseModel):
    type: Literal["dm"]
    to: str       # user_id del destinatario
    content: str
    ttl: Optional[int] = None
    allow_read_receipt: bool = True


class WsMarkRead(BaseModel):
    type: Literal["mark_read"]
    message_id: str   # ID del mensaje que el usuario leyó


class WsPing(BaseModel):
    type: Literal["ping"]
