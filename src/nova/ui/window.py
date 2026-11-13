"""Main NOVA window. Layout only; behaviour is connected in later steps."""

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from nova import __version__


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"NOVA {__version__}")
        self.resize(560, 640)

        self.transcript = QTextBrowser()
        self.status = QLabel("Ready")
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a question and press Enter")
        self.send_button = QPushButton("Send")
        self.talk_button = QPushButton("Hold to talk")
        self.stop_button = QPushButton("Stop speaking")

        input_row = QHBoxLayout()
        input_row.addWidget(self.input)
        input_row.addWidget(self.send_button)

        controls = QHBoxLayout()
        controls.addWidget(self.talk_button)
        controls.addWidget(self.stop_button)
        controls.addStretch()
        controls.addWidget(self.status)

        layout = QVBoxLayout()
        layout.addWidget(self.transcript)
        layout.addLayout(input_row)
        layout.addLayout(controls)

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)
