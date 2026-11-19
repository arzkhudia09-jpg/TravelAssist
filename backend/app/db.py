from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def make_session_factory(database_url: str):
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    url = make_url(database_url)
    backend = url.get_backend_name()
    if backend not in {"sqlite", "postgresql"}:
        raise RuntimeError(f"Unsupported database backend: {backend}")

    if backend == "sqlite":
        connect_args = {"check_same_thread": False}
        engine = create_engine(
            url,
            connect_args=connect_args,
            pool_pre_ping=True,
        )
    else:
        if url.drivername == "postgres":
            url = url.set(drivername="postgresql+psycopg")
        elif url.drivername not in {"postgresql", "postgresql+psycopg"}:
            raise RuntimeError("Use a PostgreSQL URL with the psycopg driver")
        if not url.database:
            raise RuntimeError("DATABASE_URL must include a database name")
        connect_args = {
            "connect_timeout": 10,
            "application_name": "travel-assist",
        }
        if "sslmode" not in url.query:
            connect_args["sslmode"] = "require"
        engine = create_engine(
            url,
            connect_args=connect_args,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=5,
            max_overflow=5,
            pool_timeout=15,
        )
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
