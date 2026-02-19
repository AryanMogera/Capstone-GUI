from PySide6.QtWidgets import QApplication
from gui.main_window import MainWindow
import sys


def main() -> None:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(900, 520)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
