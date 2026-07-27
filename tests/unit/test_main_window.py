from datetime import datetime

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QFileDialog, QFrame, QMessageBox, QScrollArea
from PySide6.QtCore import Qt

from dataexport_studio.ui.main_window import DropdownBox, MainWindow


def configure_sqlite(window, tmp_path):
    database = tmp_path / "database.sqlite"
    database.touch()
    window.database_type.setCurrentText("SQLite")
    window.database.setText(str(database))
    return database


def test_main_window_starts_with_data_controls_disabled(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert not window.table.isEnabled()
    assert not window.export_button.isEnabled()
    assert not window.disconnect_button.isEnabled()
    assert window.progress.value() == 0
    assert window.progress.maximum() == 100
    assert window.progress.format() == "%p%"
    assert window.connection_status.property("state") == "idle"
    assert window.database_type.currentText() == "SQL Server"
    assert window.port.text() == "1433"
    assert window.windowTitle() == "DataExport Studio | 数导工坊"
    assert window.connect_button.cursor().shape() is Qt.CursorShape.PointingHandCursor
    assert window.add_filter_button.cursor().shape() is Qt.CursorShape.PointingHandCursor


def test_main_window_keeps_content_scrollable_when_height_is_small(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(700, 480)
    window.show()

    scroll_area = window.centralWidget()
    assert isinstance(scroll_area, QScrollArea)
    assert scroll_area.widget().minimumHeight() >= 1_060
    assert scroll_area.verticalScrollBarPolicy().name == "ScrollBarAsNeeded"
    assert scroll_area.verticalScrollBar().maximum() > 0


def test_successful_connection_can_be_exited(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    configure_sqlite(window, tmp_path)

    window._connect()

    assert window.disconnect_button.isEnabled()
    assert window.connection_status.property("state") == "success"

    window._disconnect()

    assert window._engine is None
    assert not window.disconnect_button.isEnabled()
    assert window.connection_status.property("state") == "idle"


def test_close_disposes_idle_database_engine(qtbot):
    class Engine:
        def __init__(self):
            self.disposed = False

        def dispose(self):
            self.disposed = True

    window = MainWindow()
    qtbot.addWidget(window)
    engine = Engine()
    window._engine = engine
    event = QCloseEvent()

    window.closeEvent(event)

    assert event.isAccepted()
    assert engine.disposed
    assert window._engine is None


def test_close_during_export_requests_cancellation_and_stays_open(qtbot, monkeypatch):
    class Worker:
        def __init__(self):
            self.cancelled = False

        def cancel(self):
            self.cancelled = True

    window = MainWindow()
    qtbot.addWidget(window)
    worker = Worker()
    window._thread = object()
    window._worker = worker
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)
    event = QCloseEvent()

    window.closeEvent(event)

    assert worker.cancelled
    assert not event.isAccepted()


def test_non_sqlite_disables_file_field_and_hides_spin_buttons(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.database_type.setCurrentText("MySQL / MariaDB")

    assert not window.database.isEnabled()
    assert window.port.validator().bottom() == 1
    assert window.port.validator().top() == 65535
    assert window.max_rows.text() == "1000000"
    assert window.max_rows.validator().bottom() == 1
    assert window.max_rows.validator().top() == 1_000_000

    window.port.clear()
    assert window._config().port is None


def test_mongodb_uses_default_port_and_allows_anonymous_connection_fields(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.database_type.setCurrentText("MongoDB")

    assert window.port.text() == "27017"
    assert window.host.isEnabled()
    assert window.port.isEnabled()
    assert window.username.isEnabled()
    assert window.password.isEnabled()
    assert not window.database.isEnabled()
    assert not window.sqlite_choose_button.isEnabled()


def test_sqlite_file_picker_populates_an_existing_path(qtbot, monkeypatch, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    sqlite_file = tmp_path / "selected.sqlite"
    sqlite_file.touch()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: (str(sqlite_file), "SQLite 文件 (*.sqlite)"))

    window.database_type.setCurrentText("SQLite")
    window._choose_sqlite_file()

    assert window.database.text() == str(sqlite_file)
    assert window.sqlite_choose_button.isEnabled()

    window.database_type.setCurrentText("MySQL / MariaDB")
    assert not window.sqlite_choose_button.isEnabled()


def test_password_toggle_reveals_and_hides_password(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.password.setText("secret")

    window.password_toggle_action.trigger()

    assert window.password.echoMode() is window.password.EchoMode.Normal
    assert window.password_toggle_action.toolTip() == "隐藏密码"

    window.password_toggle_action.trigger()

    assert window.password.echoMode() is window.password.EchoMode.Password
    assert window.password_toggle_action.toolTip() == "显示密码"


def test_dropdown_tracks_popup_open_state(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    window.database_type.showPopup()

    assert window.database_type._popup_open

    window.database_type.hidePopup()

    assert not window.database_type._popup_open


def test_dropdown_ignores_mouse_wheel_selection_changes(qtbot):
    class WheelEvent:
        def __init__(self):
            self.ignored = False

        def ignore(self):
            self.ignored = True

    window = MainWindow()
    qtbot.addWidget(window)
    window.database_type.setCurrentIndex(0)
    event = WheelEvent()

    window.database_type.wheelEvent(event)

    assert event.ignored
    assert window.database_type.currentIndex() == 0


def test_dropdowns_are_editable_and_match_typed_substrings(qtbot):
    dropdown = DropdownBox()
    qtbot.addWidget(dropdown)
    dropdown.addItems(["config_info", "config_tags", "users"])

    dropdown.lineEdit().setText("tag")
    dropdown.completer().setCompletionPrefix("tag")

    assert dropdown.isEditable()
    assert dropdown.insertPolicy() is dropdown.InsertPolicy.NoInsert
    assert dropdown.completer().completionCount() == 1
    assert dropdown.completer().currentCompletion() == "config_tags"


def test_window_return_shortcut_tests_and_connects(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    configure_sqlite(window, tmp_path)
    window.show()

    qtbot.keyClick(window, Qt.Key.Key_Return)

    assert window.connection_status.property("state") == "success"


def test_filter_and_sort_controls_follow_their_enable_checkboxes(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)

    assert len(window.filter_rows) == 1
    assert not window.sort_options.isHidden()
    assert not window.sort_column.isEnabled()
    assert not window.sort_direction.isEnabled()
    assert not window.add_filter_button.isEnabled()
    assert not window.filter_logic.isEnabled()
    assert not window.filter_rows[0]["field"].isEnabled()

    configure_sqlite(window, tmp_path)
    window._connect()

    assert not window.sort_column.isEnabled()
    assert not window.sort_direction.isEnabled()
    assert not window.add_filter_button.isEnabled()
    assert not window.filter_rows[0]["field"].isEnabled()

    window.enable_filter.setChecked(True)
    assert window.add_filter_button.isEnabled()
    assert window.filter_rows[0]["field"].isEnabled()

    window._add_filter_row()
    assert len(window.filter_rows) == 2
    assert window.filter_logic.isEnabled()

    window._remove_filter_row(window.filter_rows[-1]["row"])
    assert len(window.filter_rows) == 1

    window.sort_enabled.setChecked(True)
    assert window.sort_column.isEnabled()
    assert window.sort_direction.isEnabled()


def test_filter_section_grows_and_keeps_the_export_section_below(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    initial_height = window.filter_section.minimumHeight()

    for _ in range(3):
        window._add_filter_row()
    qtbot.wait(50)

    sections = window.findChildren(QFrame, "section")
    export_section = sections[3]
    assert window.filter_section.minimumHeight() > initial_height
    assert window.filter_section.geometry().bottom() < export_section.geometry().top()


def test_export_file_name_defaults_to_selected_database_and_can_be_customized(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    configure_sqlite(window, tmp_path)

    window._connect()
    window.table.addItem("people")
    window.table.setCurrentText("people")
    window._set_default_file_name()

    assert window.file_name.text() == f"main-people-{datetime.now():%Y%m%d}.xlsx"

    window.file_name.setText("custom.xlsx")
    window._mark_file_name_customized(window.file_name.text())
    window._set_default_file_name()

    assert window.file_name.text() == "custom.xlsx"


def test_export_progress_uses_the_query_total(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window._on_total_ready(1_500, 1_000)
    assert window.progress.value() == 0
    assert "共 1500 行" in window.result.text()

    window._on_progress(500)
    assert window.progress.value() == 50
    assert "500/1000 行" in window.result.text()

    window._export_finished(500, 0.2)
    assert window.progress.value() == 100
    assert window.result.property("state") == "success"

    window._export_failed("导出已取消。")
    assert window.progress.value() == 0
    assert window.result.property("state") == "error"


def test_export_validation_is_shown_inline_with_error_style(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window._start_export()

    assert "请先连接数据库" in window.result.text()
    assert window.result.property("state") == "error"


def test_enabled_sort_or_filter_requires_complete_configuration(qtbot, tmp_path):
    class Engine:
        def dispose(self):
            pass

    window = MainWindow()
    qtbot.addWidget(window)
    window._engine = Engine()
    window.table.addItem("people")
    window.table.setCurrentText("people")
    window.export_directory.setText(str(tmp_path))
    window.file_name.setText("people.xlsx")

    window.sort_enabled.setChecked(True)
    window.sort_column.clear()
    window._start_export()
    assert "请选择排序字段" in window.result.text()
    assert window.result.property("state") == "error"

    window.sort_enabled.setChecked(False)
    window.enable_filter.setChecked(True)
    window._start_export()
    assert "完整填写每个筛选条件" in window.result.text()
    assert window.result.property("state") == "error"
