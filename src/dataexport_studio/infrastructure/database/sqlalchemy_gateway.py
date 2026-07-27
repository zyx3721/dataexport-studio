from typing import Iterator, Optional, Sequence
from pathlib import Path

from sqlalchemy import MetaData, Table, and_, create_engine, func, inspect, or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL
from sqlalchemy.exc import SQLAlchemyError

from ...domain.errors import ConnectionError, MetadataError, ValidationError
from ...domain.filters import build_filter
from ...domain.models import ConnectionConfig, DatabaseType, ExportRequest, FilterLogic, SortDirection


DEFAULT_DATABASES = {
    DatabaseType.MYSQL: None,
    DatabaseType.POSTGRESQL: "postgres",
    DatabaseType.SQLSERVER: "master",
}

CONNECT_TIMEOUT_SECONDS = 5


def create_database_engine(config: ConnectionConfig) -> Engine:
    try:
        if config.database_type is DatabaseType.SQLITE:
            if not config.database:
                raise ValidationError("SQLite 文件不能为空。")
            database_path = Path(config.database)
            if not database_path.is_file():
                raise ValidationError("SQLite 文件不存在或不是有效文件。")
            url = URL.create("sqlite+pysqlite", database=str(database_path))
        else:
            if not config.host:
                raise ValidationError("主机 / IP 不能为空。")
            if config.port is None:
                raise ValidationError("端口不能为空。")
            if not 1 <= config.port <= 65535:
                raise ValidationError("端口必须在 1-65535 之间。")
            if not config.username:
                raise ValidationError("用户名不能为空。")
            if not config.password:
                raise ValidationError("密码不能为空。")
            driver = {
                DatabaseType.MYSQL: "mysql+pymysql",
                DatabaseType.POSTGRESQL: "postgresql+psycopg",
                DatabaseType.SQLSERVER: "mssql+pymssql",
            }[config.database_type]
            database = config.database or DEFAULT_DATABASES[config.database_type]
            url = URL.create(driver, username=config.username, password=config.password, host=config.host, port=config.port, database=database)
        connect_args = {
            DatabaseType.SQLITE: {"timeout": CONNECT_TIMEOUT_SECONDS},
            DatabaseType.MYSQL: {"connect_timeout": CONNECT_TIMEOUT_SECONDS},
            DatabaseType.POSTGRESQL: {"connect_timeout": CONNECT_TIMEOUT_SECONDS},
            DatabaseType.SQLSERVER: {"login_timeout": CONNECT_TIMEOUT_SECONDS, "timeout": CONNECT_TIMEOUT_SECONDS},
        }[config.database_type]
        return create_engine(url, pool_pre_ping=True, connect_args=connect_args)
    except (KeyError, SQLAlchemyError) as exc:
        raise ConnectionError("无法创建数据库连接配置。") from exc


def test_connection(engine: Engine) -> None:
    try:
        with engine.connect() as connection:
            connection.execute(select(1))
    except SQLAlchemyError as exc:
        raise ConnectionError(_connection_failure_message(exc)) from exc


def _connection_failure_message(exc: SQLAlchemyError) -> str:
    detail = str(getattr(exc, "orig", exc))
    if "28000" in detail or "login failed" in detail.lower():
        return "SQL Server 登录失败。请检查用户名、密码及服务器是否启用 SQL Server 身份验证。"
    return "连接失败。请检查地址、端口、凭据和数据库驱动。"


def get_schemas(engine: Engine) -> Sequence[str]:
    try:
        return sorted(inspect(engine).get_schema_names())
    except SQLAlchemyError as exc:
        raise MetadataError("无法读取数据库架构。") from exc


def get_databases(engine: Engine) -> Sequence[str]:
    if engine.dialect.name != "mssql":
        return get_schemas(engine)
    try:
        with engine.connect() as connection:
            return list(connection.scalars(text("SELECT name FROM sys.databases WHERE state = 0 ORDER BY name")))
    except SQLAlchemyError as exc:
        raise MetadataError("无法读取 SQL Server 数据库列表。") from exc


def get_tables(engine: Engine, schema: Optional[str] = None) -> Sequence[str]:
    try:
        return sorted(inspect(engine).get_table_names(schema=schema))
    except SQLAlchemyError as exc:
        raise MetadataError("无法读取数据表。") from exc


def get_columns(engine: Engine, table: str, schema: Optional[str] = None) -> Sequence[str]:
    try:
        return [item["name"] for item in inspect(engine).get_columns(table, schema=schema)]
    except SQLAlchemyError as exc:
        raise MetadataError("无法读取表字段。") from exc


def count_rows(engine: Engine, request: ExportRequest) -> int:
    _, statement = _build_export_statement(engine, request)
    count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
    try:
        with engine.connect() as connection:
            return int(connection.scalar(count_statement) or 0)
    except SQLAlchemyError as exc:
        raise MetadataError("无法读取查询结果总数。") from exc


def stream_rows(engine: Engine, request: ExportRequest) -> tuple[Sequence[str], Iterator[tuple]]:
    headers, statement = _build_export_statement(engine, request)

    def rows() -> Iterator[tuple]:
        try:
            with engine.connect().execution_options(stream_results=True) as connection:
                result = connection.execute(statement)
                yield from result.yield_per(request.batch_size)
        except SQLAlchemyError as exc:
            raise MetadataError("读取数据失败。") from exc

    return headers, rows()


def _build_export_statement(engine: Engine, request: ExportRequest) -> tuple[Sequence[str], object]:
    allowed_tables = set(get_tables(engine, request.schema))
    if request.table not in allowed_tables:
        raise ValidationError("所选数据表不在当前连接的元数据中。")
    metadata = MetaData()
    try:
        table = Table(request.table, metadata, schema=request.schema, autoload_with=engine)
    except SQLAlchemyError as exc:
        raise MetadataError("无法读取所选数据表。") from exc
    statement = select(table)
    conditions = tuple(condition for condition in (request.filter_condition, *request.filter_conditions) if condition)
    if conditions:
        expressions = []
        for condition in conditions:
            if condition.column not in table.c:
                raise ValidationError("所选筛选字段不在当前数据表中。")
            expressions.append(build_filter(table.c[condition.column], condition))
        try:
            filter_logic = FilterLogic(request.filter_logic)
        except ValueError as exc:
            raise ValidationError("筛选条件连接方式无效。") from exc
        statement = statement.where(or_(*expressions) if filter_logic is FilterLogic.OR else and_(*expressions))
    if request.sort_column:
        if request.sort_column not in table.c:
            raise ValidationError("所选排序字段不在当前数据表中。")
        column = table.c[request.sort_column]
        try:
            sort_direction = SortDirection(request.sort_direction)
        except ValueError as exc:
            raise ValidationError("排序方式无效。") from exc
        statement = statement.order_by(column.desc() if sort_direction is SortDirection.DESCENDING else column.asc())

    return list(table.c.keys()), statement
