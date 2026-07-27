from dataclasses import replace
from datetime import datetime
from pathlib import Path
import re
from typing import Optional

import qtawesome as qta
from PySide6.QtCore import QEvent, QThread, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..domain.errors import DataExportError
from ..domain.models import (
    ConnectionConfig,
    DatabaseType,
    ExportRequest,
    FilterCondition,
    FilterLogic,
    FilterOperator,
    SortDirection,
)
from ..infrastructure.database.database_gateway import (
    create_database_engine,
    get_columns,
    get_databases,
    get_tables,
    test_connection,
)
from .export_worker import ExportWorker
from .layout_factory import build_connection_group, build_data_group, build_export_group, build_filter_group, build_header
from .widgets import DropdownBox, StyledCheckBox


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._engine = None
        self._thread: Optional[QThread] = None
        self._worker: Optional[ExportWorker] = None
        self._progress_value = 0
        self._export_total = 0
        self.setWindowTitle("DataExport Studio | 数导工坊")
        self.setMinimumSize(680, 520)
        self.resize(1180, 820)
        self._build_ui()
        self._apply_button_cursors()
        self._apply_style()
        self._update_connection_fields()
        self._set_data_controls_enabled(False)
        self._set_default_file_name()
        QApplication.instance().installEventFilter(self)
        QTimer.singleShot(0, self._reset_scroll_position)

    def _build_ui(self):
        content = QWidget()
        content.setObjectName("content")
        self._content_minimum_height = 1_060
        content.setMinimumSize(960, self._content_minimum_height)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(56, 32, 56, 44)
        layout.setSpacing(20)
        layout.addWidget(build_header())
        layout.addWidget(build_connection_group(self))
        layout.addWidget(build_data_group(self))
        layout.addWidget(build_filter_group(self))
        layout.addWidget(build_export_group(self))
        layout.addStretch(1)
        scroll_area = QScrollArea()
        scroll_area.setObjectName("mainScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setWidget(content)
        self._content_scroll = scroll_area
        self.setCentralWidget(scroll_area)
        QTimer.singleShot(0, self._sync_content_height)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._reset_scroll_position)

    def closeEvent(self, event):
        if self._thread:
            choice = QMessageBox.question(
                self,
                "导出进行中",
                "导出任务仍在进行。是否取消导出？任务停止前不会关闭程序。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if choice is QMessageBox.StandardButton.Yes:
                self._cancel_export()
            event.ignore()
            return
        if self._engine:
            self._engine.dispose()
            self._engine = None
        event.accept()

    def eventFilter(self, watched, event):
        if (
            event.type() is QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and isinstance(watched, QWidget)
            and watched.window() is self
            and self.connect_button.isEnabled()
        ):
            self.connect_button.click()
            return True
        return super().eventFilter(watched, event)

    def _reset_scroll_position(self):
        if hasattr(self, "_content_scroll"):
            self._content_scroll.verticalScrollBar().setValue(0)

    def _add_filter_row(self):
        row = QWidget()
        row.setObjectName("filterRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        field = DropdownBox()
        operator = DropdownBox()
        operator.addItems([item.value for item in FilterOperator])
        value = QLineEdit()
        value.setPlaceholderText("值；输入 NULL 表示空值")
        remove = QPushButton()
        remove.setObjectName("removeFilterButton")
        remove.setIcon(qta.icon("fa5s.times", color="#8B2C2C"))
        remove.setToolTip("移除筛选条件")
        remove.setAccessibleName("移除筛选条件")
        remove.setFixedWidth(42)
        remove.setMinimumHeight(38)
        remove.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        remove.clicked.connect(lambda: self._remove_filter_row(row))
        layout.addWidget(field, 2)
        layout.addWidget(operator, 1)
        layout.addWidget(value, 3)
        layout.addWidget(remove)
        self.filter_rows.append({"row": row, "field": field, "operator": operator, "value": value, "remove": remove})
        self.filter_rows_layout.addWidget(row)
        self._refresh_filter_rows()
        self._update_filter_section_height()

    def _remove_filter_row(self, row):
        if len(self.filter_rows) == 1:
            self.filter_rows[0]["field"].setCurrentIndex(-1)
            self.filter_rows[0]["value"].clear()
            return
        item = next(item for item in self.filter_rows if item["row"] is row)
        self.filter_rows.remove(item)
        self.filter_rows_layout.removeWidget(row)
        row.deleteLater()
        self._refresh_filter_rows()
        self._update_filter_section_height()

    def _update_filter_section_height(self):
        additional_height = sum(
            item["row"].sizeHint().height() + self.filter_rows_layout.spacing()
            for item in self.filter_rows[1:]
        )
        self.filter_section.setMinimumHeight(self._filter_section_base_height + additional_height)
        self.filter_section.updateGeometry()
        if not hasattr(self, "_content_scroll"):
            return
        QTimer.singleShot(0, self._sync_content_height)

    def _sync_content_height(self):
        content = self._content_scroll.widget()
        content.layout().invalidate()
        content.layout().activate()
        content.setMinimumHeight(max(self._content_minimum_height, content.layout().minimumSize().height()))
        content.updateGeometry()


    def _refresh_filter_rows(self):
        enabled = self._engine is not None and self.enable_filter.isChecked()
        columns = self._available_columns()
        for item in self.filter_rows:
            selected = item["field"].currentText()
            item["field"].blockSignals(True)
            item["field"].clear()
            item["field"].addItems(columns)
            item["field"].setCurrentText(selected)
            item["field"].blockSignals(False)
            item["field"].setEnabled(enabled)
            item["operator"].setEnabled(enabled)
            item["value"].setEnabled(enabled)
            item["remove"].setEnabled(enabled and len(self.filter_rows) > 1)
        self.add_filter_button.setEnabled(enabled)
        self.filter_logic.setEnabled(enabled and len(self.filter_rows) > 1)

    def _update_filter_state(self, _enabled):
        self._refresh_filter_rows()

    def _available_columns(self):
        return [self.column_name_at(index) for index in range(self.sort_column.count())]

    def column_name_at(self, index):
        return self.sort_column.itemText(index)

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QScrollArea#mainScrollArea { background: #F7F3E7; color: #182843; }
            QWidget#content { background: #F7F3E7; }
            QFrame#header { border-bottom: 2px solid #1A2A43; }
            QFrame#section { background: #FFFDFC; border: 2px solid #1A2A43; border-radius: 0; }
            QLabel { color: #182843; font-family: "Microsoft YaHei UI"; }
            QLabel#title { font-family: "Bahnschrift SemiBold"; font-size: 28px; font-weight: 800; color: #172742; letter-spacing: 0; }
            QLabel#subtitle { color: #00A88E; font-family: "Consolas"; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
            QLabel#sectionNumber { color: #6464E9; font-family: "Consolas"; font-size: 12px; font-weight: 700; }
            QLabel#sectionTitle { font-size: 18px; font-weight: 800; margin-left: 8px; }
            QLabel#fieldLabel { color: #66738B; font-size: 12px; }
            QLabel#status { color: #66738B; padding-left: 6px; }
            QLabel#status[state="idle"] { color: #66738B; }
            QLabel#status[state="warning"] { color: #A65B00; font-weight: 700; }
            QLabel#status[state="error"] { color: #B42318; font-weight: 700; }
            QLabel#status[state="success"] { color: #007D68; font-weight: 700; }
            QLineEdit, QComboBox { min-height: 38px; border: 2px solid #1A2A43; border-radius: 0; padding: 1px 10px; background: #FFFFFF; color: #1B2940; selection-background-color: #6464E9; }
            QLineEdit:focus, QComboBox:focus { border-color: #5D5CE2; background: #FFFEFC; }
            QLineEdit:disabled, QComboBox:disabled { border-color: #B8BFCA; color: #9AA4B3; background: #F2F0E9; }
            QComboBox::drop-down { border: 0; width: 28px; }
            QComboBox QAbstractItemView { background: #FFFFFF; color: #1B2940; border: 2px solid #1A2A43; selection-background-color: #E7E6FF; }
            QPushButton { min-height: 38px; border: 2px solid #1A2A43; border-radius: 0; padding: 0 18px; background: #5D5CE2; color: #FFFFFF; font-family: "Microsoft YaHei UI"; font-weight: 800; }
            QPushButton:hover:enabled { background: #4847C7; }
            QPushButton:pressed:enabled { background: #3A399E; }
            QPushButton:disabled { background: #ECEBE5; border-color: #A8B0BC; color: #9AA4B3; }
            QPushButton#connectButton:disabled { background: #5D5CE2; border-color: #1A2A43; color: #FFFFFF; }
            QPushButton#disconnectButton { background: #FFFFFF; color: #3F3DA2; border-color: #5D5CE2; }
            QPushButton#disconnectButton:hover:enabled { background: #F0EFFF; }
            QPushButton#disconnectButton:disabled { background: #ECEBE5; border-color: #A8B0BC; color: #9AA4B3; }
            QCheckBox { color: #182843; spacing: 8px; font-weight: 700; }
            QProgressBar { min-height: 20px; border: 2px solid #1A2A43; border-radius: 0; text-align: center; background: #E7EDF4; color: #182843; font-weight: 800; }
            QProgressBar::chunk { background: #00A88E; }
            QScrollBar:vertical { width: 10px; background: #F7F3E7; margin: 0; }
            QScrollBar::handle:vertical { min-height: 36px; background: #9AA4B3; border: 2px solid #F7F3E7; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

    def _apply_button_cursors(self):
        for button in self.findChildren(QAbstractButton):
            button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def _toggle_password_visibility(self):
        visible = self.password.echoMode() is QLineEdit.EchoMode.Normal
        self.password.setEchoMode(QLineEdit.EchoMode.Password if visible else QLineEdit.EchoMode.Normal)
        self.password_toggle_action.setIcon(
            qta.icon("fa5s.eye" if visible else "fa5s.eye-slash", color="#52627A")
        )
        self.password_toggle_action.setToolTip("显示密码" if visible else "隐藏密码")

    def _config(self):
        port_text = self.port.text().strip()
        database_type = self._database_type()
        return ConnectionConfig(
            database_type=database_type,
            host=self.host.text().strip(),
            port=int(port_text) if port_text else None,
            database=self._selected_database() if database_type is DatabaseType.SQLSERVER else self.database.text().strip(),
            username=self.username.text().strip(),
            password=self.password.text(),
        )

    def _update_connection_fields(self):
        is_sqlite = self.database_type.currentText() == DatabaseType.SQLITE.value
        self.host.setEnabled(not is_sqlite)
        self.port.setEnabled(not is_sqlite)
        self.username.setEnabled(not is_sqlite)
        self.password.setEnabled(not is_sqlite)
        self.database.setEnabled(is_sqlite)
        self.sqlite_choose_button.setEnabled(is_sqlite)
        self.database.setPlaceholderText("SQLite 请填写数据库文件路径" if is_sqlite else "仅 SQLite 需要配置文件路径")
        defaults = {
            DatabaseType.MYSQL.value: 3306,
            DatabaseType.POSTGRESQL.value: 5432,
            DatabaseType.SQLSERVER.value: 1433,
            DatabaseType.MONGODB.value: 27017,
        }
        self.port.setText(str(defaults.get(self.database_type.currentText(), "")))

    def _choose_sqlite_file(self):
        initial_path = self.database.text().strip() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 SQLite 文件",
            initial_path,
            "SQLite 文件 (*.db *.sqlite *.sqlite3);;所有文件 (*)",
        )
        if path:
            self.database.setText(path)

    def _set_connection_status(self, message, state):
        self.connection_status.setText(message)
        self.connection_status.setProperty("state", state)
        self.connection_status.style().unpolish(self.connection_status)
        self.connection_status.style().polish(self.connection_status)

    def _set_export_status(self, message, state):
        self.result.setText(message)
        self.result.setProperty("state", state)
        self.result.style().unpolish(self.result)
        self.result.style().polish(self.result)

    def _connect(self):
        self.connect_button.setEnabled(False)
        QApplication.processEvents()
        previous_engine = self._engine
        engine = None
        try:
            self._set_connection_status("正在连接…", "warning")
            engine = create_database_engine(self._config())
            test_connection(engine)
            if previous_engine and previous_engine is not engine:
                previous_engine.dispose()
            self._engine = engine
            self._set_connection_status("连接成功，可选择数据库和数据表", "success")
            self.disconnect_button.setEnabled(True)
            self._set_data_controls_enabled(True)
            self.schema.blockSignals(True)
            self.schema.clear()
            databases = get_databases(engine)
            self.schema.addItems(databases or [""])
            self.schema.blockSignals(False)
            self._load_tables()
        except DataExportError as exc:
            if engine is not None and engine is not self._engine:
                engine.dispose()
            if previous_engine is not None and previous_engine is not engine:
                previous_engine.dispose()
            self._engine = None
            self.disconnect_button.setEnabled(False)
            self._set_data_controls_enabled(False)
            self._set_connection_status(str(exc), "error")
        finally:
            self.connect_button.setEnabled(True)

    def _disconnect(self):
        if self._thread:
            self._set_connection_status("导出进行中，暂不能退出连接。", "warning")
            return
        if self._engine:
            self._engine.dispose()
        self._engine = None
        self.schema.clear()
        self.table.clear()
        self.sort_column.clear()
        self.disconnect_button.setEnabled(False)
        self._set_data_controls_enabled(False)
        self._set_connection_status("已退出连接", "idle")

    def _load_tables(self):
        if not self._engine:
            return
        try:
            self._switch_sqlserver_database()
            self.table.clear()
            self.table.addItems(get_tables(self._engine, self._selected_schema()))
            self._set_default_file_name()
            self._load_columns()
        except DataExportError as exc:
            self._set_connection_status(str(exc), "warning")

    def _load_columns(self):
        if not self._engine or not self.table.currentText():
            return
        try:
            columns = get_columns(self._engine, self.table.currentText(), self._selected_schema())
            selected = self.sort_column.currentText()
            self.sort_column.clear()
            self.sort_column.addItems(columns)
            self.sort_column.setCurrentText(selected)
            self._refresh_filter_rows()
            self._set_default_file_name()
        except DataExportError as exc:
            self._set_connection_status(str(exc), "warning")

    def _selected_schema(self):
        if self._database_type() is DatabaseType.SQLSERVER:
            return None
        return self.schema.currentText() or None

    def _selected_database(self):
        return self.schema.currentText().strip()

    def _database_type(self):
        return DatabaseType(self.database_type.currentText())

    def _switch_sqlserver_database(self):
        if self._database_type() is not DatabaseType.SQLSERVER:
            return
        database = self._selected_database()
        if not database or self._engine.url.database == database:
            return
        engine = create_database_engine(replace(self._config(), database=database))
        test_connection(engine)
        self._engine.dispose()
        self._engine = engine

    def _update_sort_state(self, enabled):
        self.sort_options.setVisible(True)
        self.sort_column.setEnabled(enabled and self._engine is not None)
        self.sort_direction.setEnabled(enabled and self._engine is not None)

    def _set_data_controls_enabled(self, enabled):
        self.schema.setEnabled(enabled)
        self.table.setEnabled(enabled)
        self.sort_enabled.setEnabled(enabled)
        self._update_sort_state(self.sort_enabled.isChecked())
        self._refresh_filter_rows()
        self.export_button.setEnabled(enabled)
        self.cancel_button.setEnabled(False)

    def _choose_export_directory(self):
        path = QFileDialog.getExistingDirectory(self, "选择导出目录", self.export_directory.text())
        if path:
            self.export_directory.setText(path)

    def _mark_file_name_customized(self, _text):
        self._file_name_customized = True

    def _set_default_file_name(self):
        if self._file_name_customized:
            return
        database = self._selected_database()
        table = self.table.currentText().strip()
        parts = [self._safe_file_name_part(value) for value in (database, table) if value]
        base_name = "-".join(parts) or "export"
        self.file_name.setText(f"{base_name}-{datetime.now():%Y%m%d}.xlsx")

    @staticmethod
    def _safe_file_name_part(value):
        return re.sub(r'[<>:"/\\\\|?*]+', "_", value).strip("._ ") or "export"

    def _start_export(self):
        export_directory = self.export_directory.text().strip()
        file_name = self.file_name.text().strip()
        max_rows_text = self.max_rows.text().strip()
        if not self._engine or not self.table.currentText() or not export_directory or not file_name:
            self._set_export_status("请先连接数据库、选择数据表、导出目录并填写文件名。", "error")
            return
        if not max_rows_text:
            self._set_export_status("最大行数不能为空。", "error")
            return
        try:
            max_rows = int(max_rows_text)
        except ValueError:
            self._set_export_status("最大行数必须是正整数。", "error")
            return
        if max_rows < 1:
            self._set_export_status("最大行数必须大于零。", "error")
            return
        directory = Path(export_directory)
        if not directory.is_dir():
            self._set_export_status("导出目录不存在或不可用。", "error")
            return
        if Path(file_name).name != file_name or Path(file_name).suffix.lower() not in {"", ".xlsx"}:
            self._set_export_status("文件名不能包含路径，且仅支持 .xlsx 格式。", "error")
            return
        destination = directory / (file_name if Path(file_name).suffix else f"{file_name}.xlsx")
        conditions = []
        if self.enable_filter.isChecked():
            for item in self.filter_rows:
                field = item["field"].currentText().strip()
                operator = item["operator"].currentText().strip()
                value = item["value"].text().strip()
                if not field or not operator or not value:
                    self._set_export_status("启用筛选后，请完整填写每个筛选条件。", "error")
                    return
                try:
                    conditions.append(FilterCondition(field, FilterOperator(operator), value))
                except ValueError:
                    self._set_export_status("筛选运算符无效，请从下拉选项中选择。", "error")
                    return
        sort_column = None
        if self.sort_enabled.isChecked():
            sort_column = self.sort_column.currentText().strip()
            if not sort_column:
                self._set_export_status("启用排序后，请选择排序字段。", "error")
                return
        request = ExportRequest(
            schema=self._selected_schema(),
            table=self.table.currentText(),
            destination=destination,
            filter_conditions=tuple(conditions),
            filter_logic=FilterLogic(self.filter_logic.currentData()),
            sort_column=sort_column,
            sort_direction=SortDirection(self.sort_direction.currentData()),
            max_rows=max_rows,
        )
        self._set_export_progress(0)
        self._export_total = 0
        self._set_export_status("正在读取查询结果总数，请稍候…", "idle")
        self.export_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self._thread = QThread(self)
        self._worker = ExportWorker(None, request, self._config())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.total_ready.connect(self._on_total_ready)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._export_finished)
        self._worker.failed.connect(self._export_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_worker)
        self._thread.start()

    def _cancel_export(self):
        if self._worker:
            self._worker.cancel()
            self._set_export_status("正在取消导出…", "warning")
            self.cancel_button.setEnabled(False)

    def _on_progress(self, count):
        progress = int(count * 100 / self._export_total) if self._export_total else 0
        self._set_export_progress(min(100, progress))
        self._set_export_status("正在导出：{}/{} 行，请勿关闭窗口。".format(count, self._export_total), "idle")

    def _on_total_ready(self, total_rows, planned_rows):
        self._export_total = planned_rows
        if total_rows > planned_rows:
            self._set_export_status("查询结果共 {} 行，本次最多导出 {} 行；正在导出，请勿关闭窗口。".format(total_rows, planned_rows), "idle")
        else:
            self._set_export_status("查询结果共 {} 行；正在导出，请勿关闭窗口。".format(total_rows), "idle")

    def _export_finished(self, count, elapsed):
        self._set_export_progress(100)
        self._set_export_status("导出完成：{} 行，耗时 {:.1f} 秒".format(count, elapsed), "success")

    def _export_failed(self, message):
        self._set_export_progress(0)
        self._set_export_status(message, "error")

    def _set_export_progress(self, value):
        self._progress_value = max(0, min(value, 100))
        self.progress.setRange(0, 100)
        self.progress.setValue(self._progress_value)

    def _cleanup_worker(self):
        self._worker = None
        self._thread = None
        self.export_button.setEnabled(self._engine is not None)
        self.cancel_button.setEnabled(False)
