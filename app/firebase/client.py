import logging
from pathlib import Path
from typing import Any

import firebase_admin
from firebase_admin import credentials

logger = logging.getLogger(__name__)


def initialize_firebase(
    *, credentials_path: str | None, project_id: str | None
) -> Any | None:
    """Inicializa Firebase Admin una sola vez y retorna la app o None si falla."""
    if firebase_admin._apps:
        return firebase_admin.get_app()

    try:
        if credentials_path:
            cred_file = Path(credentials_path)
            if not cred_file.exists():
                logger.warning(
                    "Firebase credentials file not found: %s", credentials_path
                )
            else:
                cred = credentials.Certificate(str(cred_file))
                options = {"projectId": project_id} if project_id else None
                return firebase_admin.initialize_app(cred, options=options)

        # Permite usar GOOGLE_APPLICATION_CREDENTIALS o metadata en cloud runtimes.
        cred = credentials.ApplicationDefault()
        options = {"projectId": project_id} if project_id else None
        return firebase_admin.initialize_app(cred, options=options)
    except Exception as exc:
        logger.warning("Firebase initialization failed: %s", exc)
        return None
