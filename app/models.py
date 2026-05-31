from typing import Literal, Optional

from pydantic import BaseModel


class ChatUser(BaseModel):
    id: str
    nickname: str
    joined_at: str       # ISO 8601
    is_online: bool
    public_key: Optional[str] = None


class MediaAttachment(BaseModel):
    """Archivo subido a Cloudinary y adjunto a un mensaje."""
    url: str
    public_id: str
    resource_type: Literal["image", "video", "raw"]
    format: str
    size_bytes: int
    original_filename: str
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None


class ChatMessage(BaseModel):
    """Mensaje del chat — grupal o DM."""
    id: str
    sender_id: str
    sender_nickname: str
    content: str
    type: Literal["group", "dm"]
    recipient_id: Optional[str] = None
    timestamp: str
    ttl: Optional[int] = None
    expires_at: Optional[str] = None
    allow_read_receipt: bool = True
    media: Optional[MediaAttachment] = None


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


class PublicKeyRequest(BaseModel):
    public_key: str


# ── Payloads WebSocket (cliente → servidor) ───────────────────────────────────

class WsGroupMessage(BaseModel):
    type: Literal["group_message"]
    content: str
    ttl: Optional[int] = None
    allow_read_receipt: bool = True
    media: Optional[MediaAttachment] = None


class WsDMMessage(BaseModel):
    type: Literal["dm"]
    to: str       # user_id del destinatario
    content: str
    ttl: Optional[int] = None
    allow_read_receipt: bool = True
    media: Optional[MediaAttachment] = None


class WsMarkRead(BaseModel):
    type: Literal["mark_read"]
    message_id: str


class WsPing(BaseModel):
    type: Literal["ping"]
