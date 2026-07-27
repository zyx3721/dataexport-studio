class DataExportError(Exception):
    """Expected, safe-to-display application error."""


class ValidationError(DataExportError):
    pass


class ConnectionError(DataExportError):
    pass


class MetadataError(DataExportError):
    pass


class ExportError(DataExportError):
    pass
