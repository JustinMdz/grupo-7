"""
Servicio de Cloudinary para Gestión Multimedia.

Encapsula la integración con la API de Cloudinary:
  - Inicialización del SDK
  - Subida de archivos (imágenes, video, archivos genéricos)
  - Eliminación (usado al expirar mensajes con TTL)
"""

from __future__ import annotations

import logging
import mimetypes
from typing import Literal

import cloudinary
import cloudinary.uploader

from ..config import settings
from ..models import MediaAttachment

logger = logging.getLogger(__name__)

ResourceType = Literal["image", "video", "raw"]

# Tipos permitidos
ALLOWED_IMAGE_MIMES = {
    "image/jpeg", "image/png", "image/webp", "image/gif", "image/heic",
}
ALLOWED_VIDEO_MIMES = {
    "video/mp4", "video/quicktime", "video/webm",
}
ALLOWED_RAW_MIMES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain", "text/csv",
    "application/zip",
}

ALL_ALLOWED_MIMES = ALLOWED_IMAGE_MIMES | ALLOWED_VIDEO_MIMES | ALLOWED_RAW_MIMES


# Inicialización
_initialized = False


def init_cloudinary() -> None:
    """Configura el SDK con las credenciales. Idempotente."""
    global _initialized
    if _initialized:
        return

    if not all([
        settings.cloudinary_cloud_name,
        settings.cloudinary_api_key,
        settings.cloudinary_api_secret,
    ]):
        logger.warning(
            "[cloudinary] Credenciales no configuradas. La subida de archivos no funcionará. "
            "Configura CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY y CLOUDINARY_API_SECRET."
        )
        return

    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )
    _initialized = True
    logger.info("[cloudinary] SDK inicializado para cloud '%s'.", settings.cloudinary_cloud_name)


def is_configured() -> bool:
    return _initialized


# Helpers
def _classify(mime_type: str) -> ResourceType | None:
    """Mapea un MIME type al resource_type de Cloudinary, o None si no se permite."""
    if mime_type in ALLOWED_IMAGE_MIMES:
        return "image"
    if mime_type in ALLOWED_VIDEO_MIMES:
        return "video"
    if mime_type in ALLOWED_RAW_MIMES:
        return "raw"
    return None


def guess_mime(filename: str, fallback: str | None = None) -> str:
    """Adivina el MIME a partir del nombre, con un fallback opcional del request."""
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or fallback or "application/octet-stream"


# Subida
class UploadError(Exception):
    """Error genérico de subida — el router lo convierte en HTTPException."""
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def upload_file(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    user_id: str,
) -> MediaAttachment:
    """
    Sube `file_bytes` a Cloudinary y retorna un MediaAttachment.

    Lanza UploadError si:
      - El SDK no está configurado
      - El MIME type no está permitido
      - El tamaño excede el límite
      - La subida falla
    """
    if not _initialized:
        raise UploadError(
            "CLOUDINARY_NOT_CONFIGURED",
            "El servicio de archivos no está configurado en el servidor.",
            status_code=503,
        )

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise UploadError(
            "FILE_TOO_LARGE",
            f"El archivo excede el límite de {settings.max_upload_size_mb} MB.",
        )

    if len(file_bytes) == 0:
        raise UploadError("EMPTY_FILE", "El archivo está vacío.")

    resource_type = _classify(mime_type)
    if resource_type is None:
        raise UploadError(
            "UNSUPPORTED_MEDIA_TYPE",
            f"El tipo '{mime_type}' no está permitido.",
            status_code=415,
        )

    try:
        result = cloudinary.uploader.upload(
            file_bytes,
            resource_type=resource_type,
            folder=f"chat/{user_id}",
            use_filename=True,
            unique_filename=True,
            overwrite=False,
            filename_override=filename,
        )
    except Exception as e:
        logger.exception("[cloudinary] Error al subir archivo: %s", e)
        raise UploadError("UPLOAD_FAILED", "No se pudo subir el archivo.", status_code=502)

    return MediaAttachment(
        url=result.get("secure_url") or result["url"],
        public_id=result["public_id"],
        resource_type=resource_type,
        format=result.get("format") or filename.rsplit(".", 1)[-1].lower(),
        size_bytes=result.get("bytes", len(file_bytes)),
        original_filename=filename,
        width=result.get("width"),
        height=result.get("height"),
        duration=result.get("duration"),
    )


# Borrado (usado al expirar TTL)
def delete_file(public_id: str, resource_type: ResourceType) -> bool:
    """
    Elimina un archivo de Cloudinary. Retorna True si OK o si ya no existía,
    False si hubo error de red u otro fallo.
    """
    if not _initialized:
        return False
    try:
        result = cloudinary.uploader.destroy(public_id, resource_type=resource_type)
        return result.get("result") in ("ok", "not found")
    except Exception as e:
        logger.warning("[cloudinary] No se pudo borrar %s: %s", public_id, e)
        return False