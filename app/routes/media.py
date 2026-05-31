"""
Ruta HTTP para subida de archivos a Cloudinary.

POST /api/chat/media/upload   (multipart/form-data, requiere Bearer token)

El cliente:
  1. Sube el archivo aquí y recibe un MediaAttachment.
  2. Envía un mensaje normal por WebSocket (group_message o dm) incluyendo
     el campo `media` con el MediaAttachment recibido.

Separar la subida del envío del mensaje permite:
  - Mostrar progreso de subida en el cliente.
  - Reintentar la subida sin reenviar el mensaje.
  - Mantener el protocolo de WS simple (JSON, sin binarios).
"""

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from ..models import MediaAttachment
from ..services import cloudinary_service

router = APIRouter()


def _get_manager(request: Request):
    return request.app.state.manager


def _require_user_id(request: Request) -> str:
    """Extrae y valida el Bearer token, retorna el user_id."""
    manager = _get_manager(request)

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
    user_id = manager.decode_token(token)
    if not user_id or not manager.get_user(user_id):
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": "Token inválido o usuario no registrado."},
        )
    return user_id


@router.post("/api/chat/media/upload", response_model=MediaAttachment)
async def upload_media(
    request: Request,
    file: UploadFile = File(...),
) -> MediaAttachment:
    user_id = _require_user_id(request)

    filename = file.filename or "archivo"
    # `file.content_type` puede venir vacío; en ese caso lo adivinamos por el nombre.
    mime_type = cloudinary_service.guess_mime(filename, fallback=file.content_type)

    try:
        file_bytes = await file.read()
    finally:
        await file.close()

    try:
        attachment = cloudinary_service.upload_file(
            file_bytes=file_bytes,
            filename=filename,
            mime_type=mime_type,
            user_id=user_id,
        )
    except cloudinary_service.UploadError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"code": e.code, "message": e.message},
        )

    return attachment