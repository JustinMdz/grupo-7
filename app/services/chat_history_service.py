from __future__ import annotations

from abc import ABC, abstractmethod
import logging

from app.config import settings
from app.firebase import FirebaseMessageRepository, initialize_firebase
from app.models import ChatMessage

logger = logging.getLogger(__name__)


class ChatHistoryStore(ABC):
    @abstractmethod
    def save_group_message(self, msg: ChatMessage) -> None:
        pass

    @abstractmethod
    def save_dm_message(self, msg: ChatMessage) -> None:
        pass

    @abstractmethod
    def get_group_messages(self, limit: int = 50) -> list[ChatMessage]:
        pass

    @abstractmethod
    def get_dm_history(
        self, user_a: str, user_b: str, limit: int = 50
    ) -> list[ChatMessage]:
        pass

    @abstractmethod
    def get_message_by_id(self, message_id: str) -> ChatMessage | None:
        pass

    @abstractmethod
    def delete_message(self, msg: ChatMessage) -> None:
        pass


class InMemoryChatHistoryStore(ChatHistoryStore):
    def __init__(self) -> None:
        self.group_messages: list[ChatMessage] = []
        self.dm_history: dict[frozenset[str], list[ChatMessage]] = {}

    def save_group_message(self, msg: ChatMessage) -> None:
        self.group_messages.append(msg)
        if len(self.group_messages) > settings.max_group_messages:
            self.group_messages = self.group_messages[-settings.max_group_messages :]

    def save_dm_message(self, msg: ChatMessage) -> None:
        if not msg.recipient_id:
            return
        key = frozenset({msg.sender_id, msg.recipient_id})
        history = self.dm_history.setdefault(key, [])
        history.append(msg)
        if len(history) > settings.max_dm_messages:
            self.dm_history[key] = history[-settings.max_dm_messages :]

    def get_group_messages(self, limit: int = 50) -> list[ChatMessage]:
        return self.group_messages[-limit:]

    def get_dm_history(
        self, user_a: str, user_b: str, limit: int = 50
    ) -> list[ChatMessage]:
        key = frozenset({user_a, user_b})
        return self.dm_history.get(key, [])[-limit:]

    def get_message_by_id(self, message_id: str) -> ChatMessage | None:
        for msg in self.group_messages:
            if msg.id == message_id:
                return msg
        for history in self.dm_history.values():
            for msg in history:
                if msg.id == message_id:
                    return msg
        return None

    def delete_message(self, msg: ChatMessage) -> None:
        if msg.type == "group":
            self.group_messages = [m for m in self.group_messages if m.id != msg.id]
            return

        if msg.recipient_id:
            key = frozenset({msg.sender_id, msg.recipient_id})
            if key in self.dm_history:
                self.dm_history[key] = [
                    m for m in self.dm_history[key] if m.id != msg.id
                ]


class FirebaseChatHistoryStore(ChatHistoryStore):
    def __init__(self, repository: FirebaseMessageRepository) -> None:
        self.repository = repository

    def save_group_message(self, msg: ChatMessage) -> None:
        self.repository.save_message(msg.model_dump())

    def save_dm_message(self, msg: ChatMessage) -> None:
        self.repository.save_message(msg.model_dump())

    def get_group_messages(self, limit: int = 50) -> list[ChatMessage]:
        docs = self.repository.get_group_messages(limit=limit)
        return [ChatMessage(**d) for d in docs]

    def get_dm_history(
        self, user_a: str, user_b: str, limit: int = 50
    ) -> list[ChatMessage]:
        docs = self.repository.get_dm_history(user_a=user_a, user_b=user_b, limit=limit)
        return [ChatMessage(**d) for d in docs]

    def get_message_by_id(self, message_id: str) -> ChatMessage | None:
        doc = self.repository.get_message_by_id(message_id)
        if not doc:
            return None
        return ChatMessage(**doc)

    def delete_message(self, msg: ChatMessage) -> None:
        self.repository.delete_message(msg.id)


class CompositeChatHistoryStore(ChatHistoryStore):
    """Sincroniza memoria + Firebase para mantener compatibilidad en runtime actual."""

    def __init__(self, primary: ChatHistoryStore, secondary: ChatHistoryStore) -> None:
        self.primary = primary
        self.secondary = secondary

    def save_group_message(self, msg: ChatMessage) -> None:
        self.primary.save_group_message(msg)
        self.secondary.save_group_message(msg)

    def save_dm_message(self, msg: ChatMessage) -> None:
        self.primary.save_dm_message(msg)
        self.secondary.save_dm_message(msg)

    def get_group_messages(self, limit: int = 50) -> list[ChatMessage]:
        data = self.primary.get_group_messages(limit)
        if data:
            return data
        return self.secondary.get_group_messages(limit)

    def get_dm_history(
        self, user_a: str, user_b: str, limit: int = 50
    ) -> list[ChatMessage]:
        data = self.primary.get_dm_history(user_a, user_b, limit)
        if data:
            return data
        return self.secondary.get_dm_history(user_a, user_b, limit)

    def get_message_by_id(self, message_id: str) -> ChatMessage | None:
        data = self.primary.get_message_by_id(message_id)
        if data:
            return data
        return self.secondary.get_message_by_id(message_id)

    def delete_message(self, msg: ChatMessage) -> None:
        self.primary.delete_message(msg)
        self.secondary.delete_message(msg)


def build_chat_history_store() -> ChatHistoryStore:
    memory_store = InMemoryChatHistoryStore()

    if not settings.firebase_enabled:
        return memory_store

    app = initialize_firebase(
        credentials_path=settings.firebase_credentials_path,
        project_id=settings.firebase_project_id,
    )
    if not app:
        logger.warning("Falling back to in-memory chat history store.")
        return memory_store

    firebase_store = FirebaseChatHistoryStore(
        FirebaseMessageRepository(settings.firebase_messages_collection)
    )
    return CompositeChatHistoryStore(primary=memory_store, secondary=firebase_store)
