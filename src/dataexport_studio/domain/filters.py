from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Column

from .errors import ValidationError
from .models import FilterCondition, FilterOperator


def build_filter(column: Column[Any], condition: FilterCondition):
    operator = condition.operator
    try:
        value_type = column.type.python_type
    except (AttributeError, NotImplementedError) as exc:
        raise ValidationError("所选筛选字段的类型不支持比较。") from exc
    value = coerce_value(condition.value, value_type)
    if value is None and operator not in (FilterOperator.EQUAL, FilterOperator.NOT_EQUAL):
        raise ValidationError("NULL 仅支持使用等于或不等于运算符筛选。")
    if operator is FilterOperator.GREATER_THAN:
        return column > value
    if operator is FilterOperator.LESS_THAN:
        return column < value
    if operator is FilterOperator.EQUAL:
        return column.is_(None) if value is None else column == value
    if operator is FilterOperator.NOT_EQUAL:
        return column.is_not(None) if value is None else column != value
    if operator is FilterOperator.GREATER_OR_EQUAL:
        return column >= value
    if operator is FilterOperator.LESS_OR_EQUAL:
        return column <= value
    if operator in (FilterOperator.CONTAINS, FilterOperator.NOT_CONTAINS):
        escaped = str(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        expression = column.like("%{}%".format(escaped), escape="\\")
        return ~expression if operator is FilterOperator.NOT_CONTAINS else expression
    raise ValidationError("不支持的筛选运算符。")


def coerce_value(raw_value: str, value_type: type) -> Any:
    if raw_value.strip().upper() == "NULL":
        return None
    try:
        if value_type is bool:
            normalized = raw_value.strip().lower()
            if normalized in {"true", "1", "yes"}:
                return True
            if normalized in {"false", "0", "no"}:
                return False
            raise ValueError
        if value_type is datetime:
            return datetime.fromisoformat(raw_value)
        if value_type is date:
            return date.fromisoformat(raw_value)
        if value_type is Decimal:
            return Decimal(raw_value)
        return value_type(raw_value)
    except (TypeError, ValueError) as exc:
        type_name = getattr(value_type, "__name__", str(value_type))
        raise ValidationError("筛选值无法转换为 {}。".format(type_name)) from exc
