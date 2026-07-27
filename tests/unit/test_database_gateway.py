import pytest

from dataexport_studio.domain.errors import ValidationError
from dataexport_studio.domain.models import ConnectionConfig, DatabaseType
from dataexport_studio.infrastructure.database import sqlalchemy_gateway
from dataexport_studio.infrastructure.database.sqlalchemy_gateway import CONNECT_TIMEOUT_SECONDS, create_database_engine


def test_mysql_connection_can_be_created_without_selecting_a_database():
    engine = create_database_engine(
        ConnectionConfig(
            database_type=DatabaseType.MYSQL,
            host="db.internal",
            port=3306,
            username="readonly",
            password="test-password",
        )
    )

    assert engine.url.database is None


def test_all_database_drivers_receive_five_second_connection_timeout(monkeypatch, tmp_path):
    calls = []

    def fake_create_engine(url, **kwargs):
        calls.append(kwargs["connect_args"])
        return object()

    monkeypatch.setattr(sqlalchemy_gateway, "create_engine", fake_create_engine)
    sqlite_file = tmp_path / "database.sqlite"
    sqlite_file.touch()
    configurations = [
        ConnectionConfig(DatabaseType.SQLITE, database=str(sqlite_file)),
        ConnectionConfig(DatabaseType.MYSQL, host="db", port=3306, username="reader", password="test-password"),
        ConnectionConfig(DatabaseType.POSTGRESQL, host="db", port=5432, username="reader", password="test-password"),
        ConnectionConfig(DatabaseType.SQLSERVER, host="db", port=1433, username="reader", password="test-password"),
    ]

    for config in configurations:
        create_database_engine(config)

    assert CONNECT_TIMEOUT_SECONDS == 5
    assert calls == [
        {"timeout": 5},
        {"connect_timeout": 5},
        {"connect_timeout": 5},
        {"login_timeout": 5, "timeout": 5},
    ]


def test_sqlserver_uses_pymssql_without_an_odbc_driver(monkeypatch):
    calls = []

    def fake_create_engine(url, **kwargs):
        calls.append((url, kwargs))
        return object()

    monkeypatch.setattr(sqlalchemy_gateway, "create_engine", fake_create_engine)
    create_database_engine(
        ConnectionConfig(DatabaseType.SQLSERVER, host="db", port=1433, username="reader", password="test-password")
    )

    url, kwargs = calls[0]
    assert url.drivername == "mssql+pymssql"
    assert dict(url.query) == {}
    assert kwargs["connect_args"] == {"login_timeout": 5, "timeout": 5}


def test_sqlserver_reads_databases_instead_of_schemas():
    class Connection:
        def scalars(self, _statement):
            return ["master", "CompanyDB"]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Engine:
        class Dialect:
            name = "mssql"

        dialect = Dialect()

        @staticmethod
        def connect():
            return Connection()

    assert sqlalchemy_gateway.get_databases(Engine()) == ["master", "CompanyDB"]


def test_connection_validation_names_the_first_missing_required_field(tmp_path):
    with pytest.raises(ValidationError, match="主机 / IP 不能为空"):
        create_database_engine(ConnectionConfig(DatabaseType.MYSQL, username="reader"))

    with pytest.raises(ValidationError, match="端口不能为空"):
        create_database_engine(ConnectionConfig(DatabaseType.MYSQL, host="db.internal", username="reader"))

    with pytest.raises(ValidationError, match="端口必须在 1-65535 之间"):
        create_database_engine(ConnectionConfig(DatabaseType.MYSQL, host="db.internal", port=65536, username="reader"))

    with pytest.raises(ValidationError, match="用户名不能为空"):
        create_database_engine(ConnectionConfig(DatabaseType.MYSQL, host="db.internal", port=3306))

    with pytest.raises(ValidationError, match="密码不能为空"):
        create_database_engine(ConnectionConfig(DatabaseType.MYSQL, host="db.internal", port=3306, username="reader"))

    with pytest.raises(ValidationError, match="SQLite 文件不能为空"):
        create_database_engine(ConnectionConfig(DatabaseType.SQLITE))

    missing_file = tmp_path / "missing.sqlite"
    with pytest.raises(ValidationError, match="SQLite 文件不存在"):
        create_database_engine(ConnectionConfig(DatabaseType.SQLITE, database=str(missing_file)))
    assert not missing_file.exists()
