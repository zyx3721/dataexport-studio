from typing import Any, Iterator, Optional, Sequence, Union

from ...domain.errors import ValidationError
from ...domain.models import ConnectionConfig, CustomSqlRequest, DatabaseType, ExportRequest, MongoAggregationRequest
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


def get_server_databases(connection: Any) -> Sequence[str]:
    if isinstance(connection, MongoConnection):
        return mongodb_gateway.get_databases(connection)
    return sqlalchemy_gateway.get_server_databases(connection)


def get_tables(connection: Any, schema: Optional[str] = None) -> Sequence[str]:
    if isinstance(connection, MongoConnection):
        return mongodb_gateway.get_tables(connection, schema)
    return sqlalchemy_gateway.get_tables(connection, schema)


def get_columns(connection: Any, table: str, schema: Optional[str] = None) -> Sequence[str]:
    if isinstance(connection, MongoConnection):
        return mongodb_gateway.get_columns(connection, table, schema)
    return sqlalchemy_gateway.get_columns(connection, table, schema)


def count_rows(connection: Any, request: Union[ExportRequest, CustomSqlRequest, MongoAggregationRequest]) -> Optional[int]:
    if isinstance(connection, MongoConnection):
        if isinstance(request, MongoAggregationRequest):
            return mongodb_gateway.count_aggregation_rows(connection, request)
        if isinstance(request, CustomSqlRequest):
            raise ValidationError("MongoDB 不支持自定义 SQL 查询。")
        return mongodb_gateway.count_rows(connection, request)
    if isinstance(request, CustomSqlRequest):
        return sqlalchemy_gateway.count_custom_sql_rows(connection, request)
    return sqlalchemy_gateway.count_rows(connection, request)


def stream_rows(connection: Any, request: Union[ExportRequest, CustomSqlRequest, MongoAggregationRequest]) -> tuple[Sequence[str], Iterator[tuple]]:
    if isinstance(connection, MongoConnection):
        if isinstance(request, MongoAggregationRequest):
            return mongodb_gateway.stream_aggregation_rows(connection, request)
        if isinstance(request, CustomSqlRequest):
            raise ValidationError("MongoDB 不支持自定义 SQL 查询。")
        return mongodb_gateway.stream_rows(connection, request)
    if isinstance(request, CustomSqlRequest):
        return sqlalchemy_gateway.stream_custom_sql_rows(connection, request)
    return sqlalchemy_gateway.stream_rows(connection, request)
