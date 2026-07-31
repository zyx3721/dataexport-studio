from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class DatabaseType(str, Enum):
    SQLITE = "SQLite"
    MYSQL = "MySQL / MariaDB"
    POSTGRESQL = "PostgreSQL"
    SQLSERVER = "SQL Server"
    MONGODB = "MongoDB"


class FilterOperator(str, Enum):
    GREATER_THAN = ">"
    LESS_THAN = "<"
    EQUAL = "="
    NOT_EQUAL = "!="
    GREATER_OR_EQUAL = ">="
    LESS_OR_EQUAL = "<="
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"


class FilterLogic(str, Enum):
    AND = "AND"
    OR = "OR"


class SortDirection(str, Enum):
    ASCENDING = "asc"
    DESCENDING = "desc"


class QueryMode(str, Enum):
    GRAPHICAL = "graphical"
    CUSTOM_SQL = "custom_sql"
    MONGODB_AGGREGATION = "mongodb_aggregation"


@dataclass(frozen=True)
class ConnectionConfig:
    database_type: DatabaseType
    host: str = ""
    port: Optional[int] = None
    database: str = ""
    username: str = ""
    password: str = ""


@dataclass(frozen=True)
class FilterCondition:
    column: str
    operator: FilterOperator
    value: str


@dataclass(frozen=True)
class ExportRequest:
    schema: Optional[str]
    table: str
    destination: Path
    filter_condition: Optional[FilterCondition] = None
    filter_conditions: tuple[FilterCondition, ...] = ()
    filter_logic: FilterLogic = FilterLogic.AND
    sort_column: Optional[str] = None
    sort_direction: SortDirection = SortDirection.ASCENDING
    max_rows: int = 1_000_000
    batch_size: int = 1_000


@dataclass(frozen=True)
class CustomSqlRequest:
    query: str
    destination: Path
    max_rows: int = 1_000_000
    batch_size: int = 1_000


@dataclass(frozen=True)
class MongoAggregationRequest:
    database: str
    collection: str
    pipeline: tuple[dict, ...]
    destination: Path
    max_rows: int = 1_000_000
    batch_size: int = 1_000
