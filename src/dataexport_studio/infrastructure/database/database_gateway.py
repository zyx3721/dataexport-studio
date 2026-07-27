from typing import Any, Iterator, Optional, Sequence

from ...domain.models import ConnectionConfig, DatabaseType, ExportRequest
from . import mongodb_gateway, sqlalchemy_gateway
from .mongodb_gateway import MongoConnection


def create_database_engine(config: ConnectionConfig) -> Any:
    if config.database_type is DatabaseType.MONGODB:
        return mongodb_gateway.create_mongodb_connection(config)
    return sqlalchemy_gateway.create_database_engine(config)


def test_connection(connection: Any) -> None:
    if isinstance(connection, MongoConnection):
        mongodb_gateway.test_connection(connection)
        return
    sqlalchemy_gateway.test_connection(connection)


def get_databases(connection: Any) -> Sequence[str]:
    if isinstance(connection, MongoConnection):
        return mongodb_gateway.get_databases(connection)
    return sqlalchemy_gateway.get_databases(connection)


def get_tables(connection: Any, schema: Optional[str] = None) -> Sequence[str]:
    if isinstance(connection, MongoConnection):
        return mongodb_gateway.get_tables(connection, schema)
    return sqlalchemy_gateway.get_tables(connection, schema)


def get_columns(connection: Any, table: str, schema: Optional[str] = None) -> Sequence[str]:
    if isinstance(connection, MongoConnection):
        return mongodb_gateway.get_columns(connection, table, schema)
    return sqlalchemy_gateway.get_columns(connection, table, schema)


def count_rows(connection: Any, request: ExportRequest) -> int:
    if isinstance(connection, MongoConnection):
        return mongodb_gateway.count_rows(connection, request)
    return sqlalchemy_gateway.count_rows(connection, request)


def stream_rows(connection: Any, request: ExportRequest) -> tuple[Sequence[str], Iterator[tuple]]:
    if isinstance(connection, MongoConnection):
        return mongodb_gateway.stream_rows(connection, request)
    return sqlalchemy_gateway.stream_rows(connection, request)
