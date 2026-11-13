from nova.ui.window import MainWindow


def test_window_has_core_controls(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle().startswith("NOVA")
    assert window.transcript.isReadOnly()
    assert window.status.text() == "Ready"
    for button in (window.send_button, window.talk_button, window.stop_button):
        assert button.isEnabled()
