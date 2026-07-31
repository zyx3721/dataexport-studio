import mongomock

from dataexport_studio.domain.models import ExportRequest, FilterCondition, FilterLogic, FilterOperator, MongoAggregationRequest, SortDirection
from dataexport_studio.infrastructure.database.mongodb_gateway import MongoConnection, count_aggregation_rows, count_rows, get_columns, get_databases, get_tables, stream_aggregation_rows, stream_rows


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


def test_mongodb_aggregation_supports_lookup(tmp_path):
    connection = mongo_connection()
    connection.client["analytics"]["departments"].insert_one({"name": "Engineering", "leader": "Grace"})
    request = MongoAggregationRequest(
        database="analytics",
        collection="employees",
        pipeline=(
            {"$lookup": {"from": "departments", "localField": "department.name", "foreignField": "name", "as": "department_info"}},
            {"$unwind": "$department_info"},
            {"$project": {"_id": 0, "员工姓名": "$name", "部门负责人": "$department_info.leader"}},
        ),
        destination=tmp_path / "employees.xlsx",
    )

    assert count_aggregation_rows(connection, request) == 1
    headers, rows = stream_aggregation_rows(connection, request)

    assert headers == ["员工姓名", "部门负责人"]
    assert list(rows) == [("Ada", "Grace")]
