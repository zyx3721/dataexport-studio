from time import monotonic
from typing import Any, Callable, Optional

from ..domain.errors import ExportError
from ..domain.models import ExportRequest
from ..infrastructure.database.database_gateway import count_rows, stream_rows
from ..infrastructure.excel.workbook_writer import write_workbook


class ExportService:
    def export(
        self,
        engine: Any,
        request: ExportRequest,
        on_total: Optional[Callable[[int, int], None]] = None,
        on_progress: Optional[Callable[[int], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> tuple[int, float]:
        started = monotonic()
        if is_cancelled and is_cancelled():
            raise ExportError("导出已取消。")
        total_rows = count_rows(engine, request)
        planned_rows = min(total_rows, request.max_rows)
        if on_total:
            on_total(total_rows, planned_rows)
        if total_rows == 0:
            raise ExportError("查询结果为空，未生成导出文件。")
        if is_cancelled and is_cancelled():
            raise ExportError("导出已取消。")
        headers, rows = stream_rows(engine, request)
        count = write_workbook(
            request.destination,
            headers,
            rows,
            request.max_rows,
            on_progress=on_progress,
            is_cancelled=is_cancelled,
        )
        return count, monotonic() - started
