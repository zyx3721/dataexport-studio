import pytest
from sqlalchemy import Column, Integer, String, Table, create_engine
from sqlalchemy import MetaData, select
from sqlalchemy.dialects import mysql

from dataexport_studio.domain.errors import ValidationError
from dataexport_studio.domain.filters import build_filter
from dataexport_studio.domain.models import FilterCondition, FilterOperator


def test_contains_escapes_like_wildcards():
    metadata = MetaData()
    table = Table("items", metadata, Column("name", String))
    statement = select(table).where(build_filter(table.c.name, FilterCondition("name", FilterOperator.CONTAINS, "100%_done")))
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "100\\%\\_done" in compiled
    assert "ESCAPE '\\'" in compiled


def test_invalid_numeric_filter_is_rejected():
    column = Column("quantity", Integer)

    with pytest.raises(ValidationError):
        build_filter(column, FilterCondition("quantity", FilterOperator.GREATER_THAN, "not-a-number"))


def test_null_filter_is_limited_to_equality():
    column = Column("quantity", Integer)

    with pytest.raises(ValidationError, match="NULL 仅支持"):
        build_filter(column, FilterCondition("quantity", FilterOperator.GREATER_THAN, "NULL"))


def test_not_equal_supports_regular_and_null_values():
    column = Column("quantity", Integer)

    regular = str(build_filter(column, FilterCondition("quantity", FilterOperator.NOT_EQUAL, "10")))
    null = str(build_filter(column, FilterCondition("quantity", FilterOperator.NOT_EQUAL, "NULL")))

    assert "!=" in regular
    assert "IS NOT NULL" in null


def test_mysql_bigint_filter_compiles_with_a_numeric_value():
    table = Table("config_info", MetaData(), Column("id", mysql.BIGINT))

    statement = select(table).where(
        build_filter(table.c.id, FilterCondition("id", FilterOperator.GREATER_THAN, "52"))
    )
    compiled = str(statement.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}))

    assert "config_info.id > 52" in compiled
