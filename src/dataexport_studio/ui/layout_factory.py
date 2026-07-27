import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..domain.models import DatabaseType, FilterLogic, SortDirection
from .widgets import DropdownBox, StyledCheckBox


def build_header():
    frame = QFrame()
    frame.setObjectName("header")
    header = QVBoxLayout(frame)
    header.setContentsMargins(0, 0, 0, 16)
    header.setSpacing(2)
    title = QLabel("DATAEXPORT STUDIO")
    title.setObjectName("title")
    subtitle = QLabel("OPERATIONS ANALYZER")
    subtitle.setObjectName("subtitle")
    header.addWidget(title)
    header.addWidget(subtitle)
    return frame


def build_connection_group(window):
    grid = QGridLayout()
    grid.setHorizontalSpacing(18)
    grid.setVerticalSpacing(14)
    window.database_type = DropdownBox()
    window.database_type.addItems([item.value for item in DatabaseType])
    window.database_type.setCurrentText(DatabaseType.SQLSERVER.value)
    window.database_type.currentIndexChanged.connect(window._update_connection_fields)
    window.host = QLineEdit()
    window.port = QLineEdit()
    window.port.setValidator(QIntValidator(1, 65535, window.port))
    window.database = QLineEdit()
    window.database.setPlaceholderText("SQLite 请填写数据库文件路径")
    window.sqlite_choose_button = QPushButton("选择文件")
    window.sqlite_choose_button.clicked.connect(window._choose_sqlite_file)
    sqlite_path_control = QWidget()
    sqlite_path_layout = QHBoxLayout(sqlite_path_control)
    sqlite_path_layout.setContentsMargins(0, 0, 0, 0)
    sqlite_path_layout.setSpacing(8)
    sqlite_path_layout.addWidget(window.database, 1)
    sqlite_path_layout.addWidget(window.sqlite_choose_button)
    window.username = QLineEdit()
    window.password = QLineEdit()
    window.password.setEchoMode(QLineEdit.EchoMode.Password)
    window.password_toggle_action = window.password.addAction(
        qta.icon("fa5s.eye", color="#52627A"),
        QLineEdit.ActionPosition.TrailingPosition,
    )
    window.password_toggle_action.setToolTip("显示密码")
    window.password_toggle_action.triggered.connect(window._toggle_password_visibility)
    window.connect_button = QPushButton("测试并连接")
    window.connect_button.setObjectName("connectButton")
    window.connect_button.clicked.connect(window._connect)
    window.disconnect_button = QPushButton("退出连接")
    window.disconnect_button.setObjectName("disconnectButton")
    window.disconnect_button.setEnabled(False)
    window.disconnect_button.clicked.connect(window._disconnect)
    window.connection_status = QLabel("等待连接")
    window.connection_status.setObjectName("status")
    window._set_connection_status("等待连接", "idle")
    grid.addWidget(field("数据库类型", window.database_type), 0, 0)
    grid.addWidget(field("主机 / IP", window.host), 0, 1)
    grid.addWidget(field("端口", window.port), 0, 2)
    window.database_field = field("SQLite 文件", sqlite_path_control)
    grid.addWidget(window.database_field, 1, 0)
    grid.addWidget(field("用户名", window.username), 1, 1)
    grid.addWidget(field("密码", window.password), 1, 2)
    grid.setColumnStretch(0, 1)
    grid.setColumnStretch(1, 1)
    grid.setColumnStretch(2, 1)
    actions = QHBoxLayout()
    actions.setContentsMargins(0, 0, 0, 0)
    actions.setSpacing(12)
    actions.addWidget(window.connect_button)
    actions.addWidget(window.disconnect_button)
    actions.addWidget(window.connection_status, 1)
    grid.addLayout(actions, 2, 0, 1, 3)
    return section("01", "连接配置", grid, 316)


def build_data_group(window):
    grid = QGridLayout()
    grid.setHorizontalSpacing(18)
    window.schema = DropdownBox()
    window.schema.currentIndexChanged.connect(window._load_tables)
    window.table = DropdownBox()
    window.table.currentIndexChanged.connect(window._load_columns)
    window.sort_enabled = StyledCheckBox("按字段排序")
    window.sort_enabled.toggled.connect(window._update_sort_state)
    window.sort_column = DropdownBox()
    window.sort_direction = DropdownBox()
    window.sort_direction.addItem("升序", SortDirection.ASCENDING)
    window.sort_direction.addItem("降序", SortDirection.DESCENDING)
    sort_control = QWidget()
    sort_layout = QVBoxLayout(sort_control)
    sort_layout.setContentsMargins(0, 0, 0, 0)
    sort_layout.setSpacing(6)
    sort_heading = QHBoxLayout()
    sort_heading.setContentsMargins(0, 0, 0, 0)
    sort_label = QLabel("排序")
    sort_label.setObjectName("fieldLabel")
    sort_heading.addWidget(sort_label)
    sort_heading.addWidget(window.sort_enabled)
    sort_heading.addStretch(1)
    sort_layout.addLayout(sort_heading)
    window.sort_options = QWidget()
    options_layout = QHBoxLayout(window.sort_options)
    options_layout.setContentsMargins(0, 0, 0, 0)
    options_layout.setSpacing(8)
    options_layout.addWidget(window.sort_column, 1)
    options_layout.addWidget(window.sort_direction)
    sort_layout.addWidget(window.sort_options)
    grid.addWidget(field("数据库", window.schema), 0, 0)
    grid.addWidget(field("数据表", window.table), 0, 1)
    grid.addWidget(sort_control, 0, 2)
    grid.setColumnStretch(0, 1)
    grid.setColumnStretch(1, 1)
    grid.setColumnStretch(2, 1)
    return section("02", "数据选择", grid, 178)


def build_filter_group(window):
    body = QVBoxLayout()
    body.setSpacing(12)
    toolbar = QHBoxLayout()
    toolbar.setContentsMargins(0, 0, 0, 0)
    toolbar.setSpacing(10)
    window.add_filter_button = QPushButton()
    window.add_filter_button.setObjectName("addFilterButton")
    window.add_filter_button.setIcon(qta.icon("fa5s.plus", color="#FFFFFF"))
    window.add_filter_button.setToolTip("新增筛选条件")
    window.add_filter_button.setAccessibleName("新增筛选条件")
    window.add_filter_button.setFixedSize(38, 38)
    window.add_filter_button.clicked.connect(window._add_filter_row)
    window.enable_filter = StyledCheckBox("启用筛选")
    window.enable_filter.toggled.connect(window._update_filter_state)
    window.filter_logic = DropdownBox()
    window.filter_logic.addItem("全部满足 (AND)", FilterLogic.AND)
    window.filter_logic.addItem("任一满足 (OR)", FilterLogic.OR)
    toolbar.addWidget(window.enable_filter)
    toolbar.addWidget(window.add_filter_button)
    toolbar.addWidget(QLabel("条件连接"))
    toolbar.addWidget(window.filter_logic)
    toolbar.addStretch(1)
    body.addLayout(toolbar)
    window.filter_rows_layout = QVBoxLayout()
    window.filter_rows_layout.setContentsMargins(0, 0, 0, 0)
    window.filter_rows_layout.setSpacing(10)
    window.filter_rows = []
    body.addLayout(window.filter_rows_layout)
    window._filter_section_base_height = 222
    window.filter_section = section("03", "多字段筛选", body, window._filter_section_base_height)
    window._add_filter_row()
    return window.filter_section


def build_export_group(window):
    grid = QGridLayout()
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(10)
    grid.setColumnStretch(1, 1)
    window.export_directory = QLineEdit()
    window.export_directory.setPlaceholderText("选择导出目录")
    browse = QPushButton("选择目录")
    browse.clicked.connect(window._choose_export_directory)
    window.file_name = QLineEdit()
    window._file_name_customized = False
    window.file_name.textEdited.connect(window._mark_file_name_customized)
    window.max_rows = QLineEdit("1000000")
    window.max_rows.setValidator(QIntValidator(1, 1_000_000, window.max_rows))
    window.export_button = QPushButton("开始导出")
    window.export_button.clicked.connect(window._start_export)
    window.cancel_button = QPushButton("取消")
    window.cancel_button.clicked.connect(window._cancel_export)
    window.progress = QProgressBar()
    window.progress.setTextVisible(True)
    window.progress.setRange(0, 100)
    window.progress.setValue(0)
    window.progress.setFormat("%p%")
    window.result = QLabel("导出任务尚未开始")
    window.result.setObjectName("status")
    window.result.setProperty("state", "idle")
    path_layout = QHBoxLayout()
    path_layout.setContentsMargins(0, 0, 0, 0)
    path_layout.setSpacing(10)
    path_layout.addWidget(window.export_directory, 1)
    path_layout.addWidget(browse)
    actions = QHBoxLayout()
    actions.setContentsMargins(0, 0, 0, 0)
    actions.setSpacing(10)
    actions.addStretch(1)
    actions.addWidget(window.export_button)
    actions.addWidget(window.cancel_button)
    grid.addWidget(field("保存目录", path_layout), 0, 0, 1, 2)
    grid.addWidget(field("文件名", window.file_name), 0, 2)
    grid.addWidget(field("最大行数", window.max_rows), 0, 3)
    grid.addLayout(actions, 1, 0, 1, 4)
    grid.addWidget(window.progress, 2, 0, 1, 4)
    grid.addWidget(window.result, 3, 0, 1, 4)
    grid.setColumnStretch(0, 4)
    grid.setColumnStretch(1, 2)
    grid.setColumnStretch(2, 3)
    grid.setColumnStretch(3, 1)
    return section("04", "导出", grid, 248)


def field(label_text, control):
    container = QWidget()
    container.setObjectName("field")
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    label = QLabel(label_text)
    label.setObjectName("fieldLabel")
    layout.addWidget(label)
    if isinstance(control, QHBoxLayout):
        layout.addLayout(control)
    else:
        layout.addWidget(control)
    return container


def section(number, title, body_layout, minimum_height):
    container = QFrame()
    container.setObjectName("section")
    container.setMinimumHeight(minimum_height)
    container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    layout = QVBoxLayout(container)
    layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
    layout.setContentsMargins(28, 20, 28, 22)
    layout.setSpacing(16)
    heading = QHBoxLayout()
    heading.setContentsMargins(0, 0, 0, 0)
    number_label = QLabel(number)
    number_label.setObjectName("sectionNumber")
    title_label = QLabel(title)
    title_label.setObjectName("sectionTitle")
    heading.addWidget(number_label)
    heading.addWidget(title_label)
    heading.addStretch(1)
    layout.addLayout(heading)
    layout.addLayout(body_layout)
    return container
