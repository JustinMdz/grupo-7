from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .connection_manager import ConnectionManager
from .routes.chat import router as chat_router
from .routes.websocket import router as ws_router
from .routes.media import router as media_router
from .services import cloudinary_service

# Singleton global del manager — todos los routers lo comparten
manager = ConnectionManager()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Chat Backend",
        description="Servidor de chat en tiempo real con WebSockets. ",
        version="1.0.0",
    )

    # CORS abierto para que los alumnos puedan conectarse desde cualquier origen
    origins = (
        ["*"]
        if settings.allowed_origins == "*"
        else [o.strip() for o in settings.allowed_origins.split(",")]
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Inicializar Cloudinary
    cloudinary_service.init_cloudinary()

    # Inyectar el manager en el estado de la app para que los routers lo accedan
    app.state.manager = manager

    app.include_router(chat_router)
    app.include_router(media_router)
    app.include_router(ws_router)

    return app
