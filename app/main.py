import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.api import router
from app.background import background_task
from app.nats_client import nats_client

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

for lib in ["sqlalchemy.engine", "sqlalchemy.pool", "sqlalchemy.orm", "asyncio", "nats", "httpx", "httpcore"]:
    logging.getLogger(lib).setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.INFO)
logging.getLogger("uvicorn.error").setLevel(logging.INFO)

logger = logging.getLogger("weather_api")
logger.setLevel(logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Запуск приложения...")
    await init_db()
    logger.info("База данных инициализирована")
    
    # NATS
    try:
        await nats_client.connect()
        logger.info("Подключено к NATS")
        await nats_client.publish_system_event("app_started", {
            "timestamp": datetime.now().isoformat(),
            "version": settings.app_version
        })
    except Exception as e:
        logger.warning(f"NATS недоступен: {e}")
    
    # Фоновая задача
    await background_task.start(nats_client)
    logger.info("Фоновая задача запущена")
    
    yield
    
    # Shutdown
    logger.info("становка приложения...")
    await background_task.stop()
    logger.info("Фоновая задача остановлена")
    
    try:
        await nats_client.publish_system_event("app_stopping", {
            "timestamp": datetime.now().isoformat()
        })
        await nats_client.disconnect()
        logger.info("Отключено от NATS")
    except Exception as e:
        logger.warning(f"Ошибка отключения NATS: {e}")
    
    logger.info("Приложение остановлено")

# Создание приложения
app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1", tags=["weather"])

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": "connected",
        "nats": "connected" if nats_client.is_connected else "disconnected",
        "background_task": "running" if background_task.is_running else "stopped"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True,
        access_log=False,
        log_level="warning"
    )