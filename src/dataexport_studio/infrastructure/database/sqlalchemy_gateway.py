from typing import Iterator, Optional, Sequence
from pathlib import Path

from sqlalchemy import MetaData, Table, and_, create_engine, func, inspect, or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL
from sqlalchemy.exc import SQLAlchemyError

from ...domain.errors import ConnectionError, MetadataError, ValidationError
from ...domain.filters import build_filter
from ...domain.models import ConnectionConfig, CustomSqlRequest, DatabaseType, ExportRequest, FilterLogic, SortDirection


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
    return get_server_databases(engine)


def get_server_databases(engine: Engine) -> Sequence[str]:
    """Return databases available on the connected server, rather than schemas."""
    try:
        with engine.connect() as connection:
            if engine.dialect.name == "mssql":
                statement = "SELECT name FROM sys.databases WHERE state = 0 ORDER BY name"
                return list(connection.scalars(text(statement)))
            if engine.dialect.name in {"mysql", "mariadb"}:
                return list(connection.scalars(text("SHOW DATABASES")))
            if engine.dialect.name == "postgresql":
                statement = "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname"
                return list(connection.scalars(text(statement)))
            if engine.dialect.name == "sqlite":
                return [Path(engine.url.database).stem] if engine.url.database else []
            return []
    except SQLAlchemyError as exc:
        raise MetadataError("无法读取服务端数据库列表。") from exc


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


def count_custom_sql_rows(engine: Engine, request: CustomSqlRequest) -> Optional[int]:
    query = validate_custom_sql(request.query)
    count_query = "SELECT COUNT(*) FROM ({}) AS dataexport_query".format(query)
    try:
        with engine.connect() as connection:
            return int(connection.scalar(text(count_query)) or 0)
    except SQLAlchemyError:
        return None


def stream_custom_sql_rows(engine: Engine, request: CustomSqlRequest) -> tuple[Sequence[str], Iterator[tuple]]:
    query = validate_custom_sql(request.query)
    connection = None
    result = None
    try:
        connection = engine.connect().execution_options(stream_results=True)
        result = connection.execute(text(query))
        headers = _unique_headers(result.keys())
    except SQLAlchemyError as exc:
        if result is not None:
            result.close()
        if connection is not None:
            connection.close()
        raise MetadataError(_custom_sql_failure_message(exc)) from exc

    def rows() -> Iterator[tuple]:
        try:
            for row in result.yield_per(request.batch_size):
                yield tuple(row)
        except SQLAlchemyError as exc:
            raise MetadataError(_custom_sql_failure_message(exc)) from exc
        finally:
            result.close()
            connection.close()

    return headers, rows()


def validate_custom_sql(raw_query: str) -> str:
    query = raw_query.strip()
    if query.endswith(";"):
        query = query[:-1].rstrip()
    if not query:
        raise ValidationError("请输入自定义 SQL 查询。")
    tokens = _sql_tokens(query)
    if not tokens or tokens[0] not in {"SELECT", "WITH"}:
        raise ValidationError("自定义 SQL 仅允许 SELECT 或 WITH ... SELECT 查询。")
    forbidden = {"ALTER", "ATTACH", "CALL", "CREATE", "DELETE", "DETACH", "DO", "DROP", "EXEC", "EXECUTE", "GRANT", "INSERT", "MERGE", "PRAGMA", "REVOKE", "TRUNCATE", "UPDATE", "VACUUM"}
    if any(token in forbidden for token in tokens):
        raise ValidationError("自定义 SQL 仅允许只读查询，不能包含写入或管理语句。")
    if ";" in tokens:
        raise ValidationError("自定义 SQL 仅允许单条查询，不能包含多条语句。")
    if "INTO" in tokens:
        raise ValidationError("自定义 SQL 不允许 SELECT INTO。")
    if "SELECT" not in tokens:
        raise ValidationError("WITH 查询必须包含最终的 SELECT 语句。")
    return query


def _sql_tokens(query: str) -> list[str]:
    tokens = []
    index = 0
    length = len(query)
    while index < length:
        character = query[index]
        if character in "'\"":
            quote = character
            index += 1
            while index < length:
                if query[index] == quote:
                    if quote == "'" and index + 1 < length and query[index + 1] == quote:
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            continue
        if character == "[":
            index = query.find("]", index + 1)
            index = length if index < 0 else index + 1
            continue
        if query.startswith("--", index):
            newline = query.find("\n", index + 2)
            index = length if newline < 0 else newline + 1
            continue
        if query.startswith("/*", index):
            closing = query.find("*/", index + 2)
            index = length if closing < 0 else closing + 2
            continue
        if character == ";":
            tokens.append(";")
            index += 1
            continue
        if character.isalnum() or character == "_":
            end = index + 1
            while end < length and (query[end].isalnum() or query[end] == "_"):
                end += 1
            tokens.append(query[index:end].upper())
            index = end
            continue
        index += 1
    return tokens


def _unique_headers(headers: Sequence[str]) -> list[str]:
    counts = {}
    unique_headers = []
    for header in headers:
        count = counts.get(header, 0) + 1
        counts[header] = count
        unique_headers.append(header if count == 1 else "{}_{}".format(header, count))
    return unique_headers


def _custom_sql_failure_message(exc: SQLAlchemyError) -> str:
    detail = str(getattr(exc, "orig", exc)).lower()
    if "syntax" in detail or "near" in detail:
        return "自定义 SQL 语法错误，请检查关键字、括号和字段名。"
    if "permission" in detail or "not authorized" in detail or "access denied" in detail:
        return "当前账户没有执行该查询所需的只读权限。"
    if "does not exist" in detail or "no such table" in detail or "invalid object" in detail or "unknown column" in detail:
        return "查询对象不存在或当前账户无访问权限。"
    if "timeout" in detail or "timed out" in detail:
        return "自定义 SQL 查询超时。"
    return "自定义 SQL 执行失败。请检查查询语句和账户权限。"


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
