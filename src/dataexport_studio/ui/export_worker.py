from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot

from ..application.export_service import ExportService
from ..domain.errors import DataExportError
from ..domain.models import ConnectionConfig
from ..infrastructure.database.database_gateway import create_database_engine


class ExportWorker(QObject):
    total_ready = Signal(int, int)
    progress = Signal(int)
    finished = Signal(int, float)
    failed = Signal(str)

    def __init__(self, engine, request, connection_config: Optional[ConnectionConfig] = None):
        super().__init__()
        self._engine = engine
        self._request = request
        self._connection_config = connection_config
        self._cancelled = False

    @Slot()
    def run(self):
        worker_engine = None
        try:
            # SQLAlchemy pools may retain a connection opened by the UI thread.
            # Create the export connection in this worker thread instead.
            worker_engine = create_database_engine(self._connection_config) if self._connection_config else self._engine
            count, elapsed = ExportService().export(
                worker_engine,
                self._request,
                on_total=self.total_ready.emit,
                on_progress=self.progress.emit,
                is_cancelled=lambda: self._cancelled,
            )
            self.finished.emit(count, elapsed)
        except DataExportError as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("导出失败。请检查数据库连接、筛选条件与保存路径。")
        finally:
            if self._connection_config and worker_engine is not None:
                worker_engine.dispose()

    def cancel(self):
        self._cancelled = True
