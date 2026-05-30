from __future__ import annotations

from typing import Any

from firebase_admin import firestore


class FirebaseMessageRepository:
    def __init__(self, collection_name: str) -> None:
        self._db = firestore.client()
        self._collection = self._db.collection(collection_name)

    @staticmethod
    def dm_chat_key(user_a: str, user_b: str) -> str:
        first, second = sorted([user_a, user_b])
        return f"dm:{first}:{second}"

    @staticmethod
    def chat_key_from_message(message: dict[str, Any]) -> str:
        if message.get("type") == "group":
            return "group"
        sender = str(message.get("sender_id", ""))
        recipient = str(message.get("recipient_id", ""))
        return FirebaseMessageRepository.dm_chat_key(sender, recipient)

    def save_message(self, message: dict[str, Any]) -> None:
        payload = dict(message)
        payload["chat_key"] = self.chat_key_from_message(payload)
        doc_id = str(payload["id"])
        self._collection.document(doc_id).set(payload)

    def get_group_messages(self, limit: int) -> list[dict[str, Any]]:
        docs = (
            self._collection.where("chat_key", "==", "group")
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        items = [doc.to_dict() for doc in docs]
        return list(reversed(items))

    def get_dm_history(
        self, user_a: str, user_b: str, limit: int
    ) -> list[dict[str, Any]]:
        chat_key = self.dm_chat_key(user_a, user_b)
        docs = (
            self._collection.where("chat_key", "==", chat_key)
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        items = [doc.to_dict() for doc in docs]
        return list(reversed(items))

    def get_message_by_id(self, message_id: str) -> dict[str, Any] | None:
        doc = self._collection.document(message_id).get()
        if not doc.exists:
            return None
        return doc.to_dict()

    def delete_message(self, message_id: str) -> None:
        self._collection.document(message_id).delete()
