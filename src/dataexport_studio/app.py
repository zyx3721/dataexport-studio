import ctypes
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow


def application_icon_path() -> Path:
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base_path / "assets" / "icons" / "app.ico"


def set_windows_app_user_model_id() -> None:
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Sunline.DatabaseExportStudio")


def activate_english_keyboard_layout() -> bool:
    """Switch the foreground Windows input method to English mode."""
    if sys.platform != "win32":
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    imm32 = ctypes.WinDLL("imm32", use_last_error=True)
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    input_context = imm32.ImmGetContext(hwnd)
    if not input_context:
        return False
    try:
        imm32.ImmSetOpenStatus(input_context, 0)
        return bool(imm32.ImmSetConversionStatus(input_context, 0x0409, 0))
    finally:
        imm32.ImmReleaseContext(hwnd, input_context)


def main() -> int:
    set_windows_app_user_model_id()
    application = QApplication(sys.argv)
    application.setApplicationName("DataExport Studio")
    icon = QIcon(str(application_icon_path()))
    application.setWindowIcon(icon)
    window = MainWindow()
    window.setWindowIcon(icon)
    window.show()
    QTimer.singleShot(0, activate_english_keyboard_layout)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
