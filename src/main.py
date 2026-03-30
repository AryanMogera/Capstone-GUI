# src/main.py

import sys
from PySide6.QtWidgets import QApplication
from PySide6 import QtGui
from gui.main_window import MainWindow

def apply_light_theme(app: QApplication) -> None:
    # Force a consistent light theme across platforms (incl. macOS dark mode).
    app.setStyle("Fusion")

    pal = QtGui.QPalette()
    pal.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#ffffff"))
    pal.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor("#111827"))
    pal.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor("#ffffff"))
    pal.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor("#f3f4f6"))
    pal.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor("#111827"))
    pal.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor("#ffffff"))
    pal.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor("#111827"))
    pal.setColor(QtGui.QPalette.ColorRole.ToolTipBase, QtGui.QColor("#ffffff"))
    pal.setColor(QtGui.QPalette.ColorRole.ToolTipText, QtGui.QColor("#111827"))
    pal.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor("#2563eb"))
    pal.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("#ffffff"))
    pal.setColor(QtGui.QPalette.ColorRole.Link, QtGui.QColor("#2563eb"))
    app.setPalette(pal)

    app.setStyleSheet(
        """
        QWidget { background: #ffffff; color: #111827; }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {
            background: #ffffff;
            border: 1px solid #d1d5db;
            padding: 4px 6px;
            border-radius: 6px;
        }
        QPushButton {
            background: #f9fafb;
            border: 1px solid #d1d5db;
            padding: 6px 10px;
            border-radius: 8px;
        }
        QPushButton:hover { background: #f3f4f6; }
        QPushButton:pressed { background: #e5e7eb; }
        QGroupBox {
            border: 1px solid #e5e7eb;
            border-radius: 10px;
            margin-top: 10px;
            padding: 8px;
        }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
        QTableWidget { gridline-color: #e5e7eb; }
        QHeaderView::section {
            background: #f3f4f6;
            color: #111827;
            border: 1px solid #e5e7eb;
            padding: 6px;
        }
        """
    )

def main() -> None:
    app = QApplication(sys.argv)
    apply_light_theme(app)
    win = MainWindow()
    win.resize(950, 620)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()