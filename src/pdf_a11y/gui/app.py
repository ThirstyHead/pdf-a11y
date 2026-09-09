"""Application launcher for pdf-a11y desktop GUI."""
import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from pdf_a11y.gui.main_window import MainWindow


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("pdf-a11y")
    app.setOrganizationName("ThirstyHead")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
