import json
import re
from dataclasses import dataclass
from typing import Any, Iterator, Optional, Sequence

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.errors import ConfigurationError, OperationFailure, PyMongoError

from ...domain.errors import ConnectionError, MetadataError, ValidationError
from ...domain.filters import coerce_value
from ...domain.models import ConnectionConfig, ExportRequest, FilterCondition, FilterLogic, FilterOperator, SortDirection


CONNECT_TIMEOUT_MILLISECONDS = 5_000
FIELD_SAMPLE_SIZE = 100


@dataclass
class MongoConnection:
    client: MongoClient

    def dispose(self) -> None:
        self.client.close()


def create_mongodb_connection(config: ConnectionConfig) -> MongoConnection:
    if not config.host:
        raise ValidationError("主机 / IP 不能为空。")
    if config.port is None:
        raise ValidationError("端口不能为空。")
    if not 1 <= config.port <= 65535:
        raise ValidationError("端口必须在 1-65535 之间。")
    if bool(config.username) != bool(config.password):
        raise ValidationError("MongoDB 用户名和密码需同时填写。")
    try:
        client = MongoClient(
            host=config.host,
            port=config.port,
            username=config.username or None,
            password=config.password or None,
            serverSelectionTimeoutMS=CONNECT_TIMEOUT_MILLISECONDS,
            connectTimeoutMS=CONNECT_TIMEOUT_MILLISECONDS,
        )
        return MongoConnection(client)
    except PyMongoError as exc:
        raise ConnectionError("无法创建 MongoDB 连接配置。") from exc


def test_connection(connection: MongoConnection) -> None:
    try:
        connection.client.admin.command("ping")
    except OperationFailure as exc:
        if exc.code == 18:
            raise ConnectionError("MongoDB 身份验证失败。请检查用户名、密码和认证数据库。") from exc
        raise ConnectionError("MongoDB 连接被服务器拒绝。请检查账户权限。") from exc
    except ConfigurationError as exc:
        if "wire version" in str(exc):
            raise ConnectionError("MongoDB 服务版本与当前驱动不兼容。") from exc
        raise ConnectionError("MongoDB 连接配置无效。") from exc
    except PyMongoError as exc:
        raise ConnectionError("MongoDB 连接失败。请检查地址、端口、凭据和网络。") from exc


def get_databases(connection: MongoConnection) -> Sequence[str]:
    try:
        return sorted(connection.client.list_database_names())
    except PyMongoError as exc:
        raise MetadataError("无法读取 MongoDB 数据库列表。") from exc


def get_tables(connection: MongoConnection, database: Optional[str] = None) -> Sequence[str]:
    if not database:
        raise ValidationError("请选择 MongoDB 数据库。")
    try:
        return sorted(connection.client[database].list_collection_names())
    except PyMongoError as exc:
        raise MetadataError("无法读取 MongoDB Collection 列表。") from exc


def get_columns(connection: MongoConnection, table: str, database: Optional[str] = None) -> Sequence[str]:
    collection = _get_collection(connection, database, table)
    try:
        fields = set()
        for document in collection.find({}, limit=FIELD_SAMPLE_SIZE):
            fields.update(_flatten_document(document).keys())
        return sorted(fields, key=lambda field: (field != "_id", field))
    except PyMongoError as exc:
        raise MetadataError("无法读取 MongoDB Collection 字段。") from exc


def count_rows(connection: MongoConnection, request: ExportRequest) -> int:
    collection = _get_collection(connection, request.schema, request.table)
    try:
        return int(collection.count_documents(_build_query(collection, request)))
    except PyMongoError as exc:
        raise MetadataError("无法读取 MongoDB 查询结果总数。") from exc


def stream_rows(connection: MongoConnection, request: ExportRequest) -> tuple[Sequence[str], Iterator[tuple]]:
    collection = _get_collection(connection, request.schema, request.table)
    headers = get_columns(connection, request.table, request.schema)
    query = _build_query(collection, request)

    def rows() -> Iterator[tuple]:
        try:
            cursor = collection.find(query, batch_size=request.batch_size)
            if request.sort_column:
                direction = DESCENDING if request.sort_direction is SortDirection.DESCENDING else ASCENDING
                cursor = cursor.sort(request.sort_column, direction)
            try:
                for document in cursor:
                    flattened = _flatten_document(document)
                    yield tuple(flattened.get(header) for header in headers)
            finally:
                cursor.close()
        except PyMongoError as exc:
            raise MetadataError("读取 MongoDB 数据失败。") from exc

    return headers, rows()


def _get_collection(connection: MongoConnection, database: Optional[str], table: str) -> Collection:
    if not database:
        raise ValidationError("请选择 MongoDB 数据库。")
    if not table:
        raise ValidationError("请选择 MongoDB Collection。")
    if table not in get_tables(connection, database):
        raise ValidationError("所选 Collection 不在当前数据库中。")
    return connection.client[database][table]


def _build_query(collection: Collection, request: ExportRequest) -> dict:
    conditions = tuple(condition for condition in (request.filter_condition, *request.filter_conditions) if condition)
    if not conditions:
        return {}
    available_fields = set(_collection_fields(collection))
    expressions = []
    for condition in conditions:
        if condition.column not in available_fields:
            raise ValidationError("所选筛选字段不在当前 Collection 中。")
        expressions.append(_build_condition(collection, condition))
    if request.filter_logic is FilterLogic.OR:
        return {"$or": expressions}
    return {"$and": expressions}


def _build_condition(collection: Collection, condition: FilterCondition) -> dict:
    operator = condition.operator
    if operator in (FilterOperator.CONTAINS, FilterOperator.NOT_CONTAINS):
        expression = {"$regex": re.escape(condition.value)}
        return {condition.column: {"$not": expression}} if operator is FilterOperator.NOT_CONTAINS else {condition.column: expression}
    value = _coerce_collection_value(collection, condition)
    if value is None and operator not in (FilterOperator.EQUAL, FilterOperator.NOT_EQUAL):
        raise ValidationError("NULL 仅支持使用等于或不等于运算符筛选。")
    operators = {
        FilterOperator.GREATER_THAN: "$gt",
        FilterOperator.LESS_THAN: "$lt",
        FilterOperator.NOT_EQUAL: "$ne",
        FilterOperator.GREATER_OR_EQUAL: "$gte",
        FilterOperator.LESS_OR_EQUAL: "$lte",
    }
    if operator is FilterOperator.EQUAL:
        return {condition.column: value}
    if operator in operators:
        return {condition.column: {operators[operator]: value}}
    raise ValidationError("不支持的 MongoDB 筛选运算符。")


def _coerce_collection_value(collection: Collection, condition: FilterCondition) -> Any:
    if condition.value.strip().upper() == "NULL":
        return None
    value_type = _field_value_type(collection, condition.column)
    return coerce_value(condition.value, value_type) if value_type else condition.value


def _field_value_type(collection: Collection, field: str) -> Optional[type]:
    try:
        for document in collection.find({field: {"$exists": True}}, limit=FIELD_SAMPLE_SIZE):
            value = _lookup_field(document, field)
            if value is not None:
                return type(value)
    except PyMongoError as exc:
        raise MetadataError("无法读取 MongoDB 字段类型。") from exc
    return None


def _collection_fields(collection: Collection) -> Sequence[str]:
    try:
        fields = set()
        for document in collection.find({}, limit=FIELD_SAMPLE_SIZE):
            fields.update(_flatten_document(document).keys())
        return tuple(fields)
    except PyMongoError as exc:
        raise MetadataError("无法读取 MongoDB Collection 字段。") from exc


def _flatten_document(document: dict, prefix: str = "") -> dict:
    flattened = {}
    for key, value in document.items():
        field = "{}.{}".format(prefix, key) if prefix else key
        if isinstance(value, dict):
            flattened.update(_flatten_document(value, field))
        elif isinstance(value, list):
            flattened[field] = json.dumps(value, ensure_ascii=False, default=str)
        else:
            flattened[field] = str(value) if value.__class__.__name__ == "ObjectId" else value
    return flattened


def _lookup_field(document: dict, field: str) -> Any:
    value: Any = document
    for part in field.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value
