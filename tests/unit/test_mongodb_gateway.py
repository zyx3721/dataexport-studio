import mongomock

from dataexport_studio.domain.models import ExportRequest, FilterCondition, FilterLogic, FilterOperator, SortDirection
from dataexport_studio.infrastructure.database.mongodb_gateway import MongoConnection, count_rows, get_columns, get_databases, get_tables, stream_rows


def mongo_connection():
    client = mongomock.MongoClient()
    collection = client["analytics"]["employees"]
    collection.insert_many(
        [
            {"name": "Ada", "score": 95, "department": {"name": "Engineering"}, "tags": ["python", "data"]},
            {"name": "Bob", "score": 70, "department": {"name": "Support"}, "tags": ["service"]},
        ]
    )
    return MongoConnection(client)


def test_mongodb_lists_databases_collections_and_nested_fields():
    connection = mongo_connection()

    assert get_databases(connection) == ["analytics"]
    assert get_tables(connection, "analytics") == ["employees"]
    assert get_columns(connection, "employees", "analytics") == ["_id", "department.name", "name", "score", "tags"]


def test_mongodb_filters_sorts_and_streams_documents(tmp_path):
    connection = mongo_connection()
    request = ExportRequest(
        schema="analytics",
        table="employees",
        destination=tmp_path / "employees.xlsx",
        filter_conditions=(FilterCondition("score", FilterOperator.GREATER_THAN, "80"),),
        filter_logic=FilterLogic.AND,
        sort_column="name",
        sort_direction=SortDirection.DESCENDING,
    )

    assert count_rows(connection, request) == 1
    headers, rows = stream_rows(connection, request)
    values = list(rows)

    assert headers == ["_id", "department.name", "name", "score", "tags"]
    assert values[0][1:] == ("Engineering", "Ada", 95, '["python", "data"]')
