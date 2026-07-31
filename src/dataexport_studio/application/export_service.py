from time import monotonic
from itertools import chain
from typing import Any, Callable, Optional, Union

from ..domain.errors import ExportError
from ..domain.models import CustomSqlRequest, ExportRequest, MongoAggregationRequest
from ..infrastructure.database.database_gateway import count_rows, stream_rows
from ..infrastructure.excel.workbook_writer import write_workbook


class ExportService:
    def export(
        self,
        engine: Any,
        request: Union[ExportRequest, CustomSqlRequest, MongoAggregationRequest],
        on_total: Optional[Callable[[int, int], None]] = None,
        on_progress: Optional[Callable[[int], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> tuple[int, float]:
        started = monotonic()
        if is_cancelled and is_cancelled():
            raise ExportError("导出已取消。")
        total_rows = count_rows(engine, request)
        planned_rows = min(total_rows, request.max_rows) if total_rows is not None else None
        if on_total:
            on_total(total_rows if total_rows is not None else -1, planned_rows if planned_rows is not None else -1)
        if total_rows == 0:
            raise ExportError("查询结果为空，未生成导出文件。")
        if is_cancelled and is_cancelled():
            raise ExportError("导出已取消。")
        headers, rows = stream_rows(engine, request)
        if total_rows is None:
            rows = _require_first_row(rows)
        count = write_workbook(
            request.destination,
            headers,
            rows,
            request.max_rows,
            on_progress=on_progress,
            is_cancelled=is_cancelled,
        )
        return count, monotonic() - started


def _require_first_row(rows):
    iterator = iter(rows)
    try:
        first_row = next(iterator)
    except StopIteration as exc:
        raise ExportError("查询结果为空，未生成导出文件。") from exc
    return chain((first_row,), iterator)
