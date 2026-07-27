import dataexport_studio.app as app


def test_activate_english_keyboard_layout_uses_foreground_input_context(monkeypatch):
    calls = []

    class User32:
        def GetForegroundWindow(self):
            return 123

    class Imm32:
        def ImmGetContext(self, hwnd):
            calls.append(("context", hwnd))
            return 456

        def ImmSetOpenStatus(self, input_context, status):
            calls.append(("open", input_context, status))

        def ImmSetConversionStatus(self, input_context, conversion, sentence):
            calls.append(("conversion", input_context, conversion, sentence))
            return 1

        def ImmReleaseContext(self, hwnd, input_context):
            calls.append(("release", hwnd, input_context))

    monkeypatch.setattr(app.sys, "platform", "win32")
    monkeypatch.setattr(
        app.ctypes,
        "WinDLL",
        lambda name, **_kwargs: User32() if name == "user32" else Imm32(),
    )

    assert app.activate_english_keyboard_layout()
    assert calls == [
        ("context", 123),
        ("open", 456, 0),
        ("conversion", 456, 0x0409, 0),
        ("release", 123, 456),
    ]


def test_activate_english_keyboard_layout_skips_non_windows(monkeypatch):
    monkeypatch.setattr(app.sys, "platform", "linux")

    assert not app.activate_english_keyboard_layout()


def test_application_icon_path_uses_the_bundle_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(app.sys, "_MEIPASS", str(tmp_path), raising=False)

    assert app.application_icon_path() == tmp_path / "assets" / "icons" / "app.ico"
