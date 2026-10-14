import logging

from sqlalchemy import Engine, create_engine, text

logger = logging.getLogger(__name__)


def create_db_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


def probe_database(engine: Engine) -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("Database readiness check failed: %s", type(exc).__name__)
        return False
