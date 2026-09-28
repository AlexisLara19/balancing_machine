import sys
from PyQt6.QtWidgets import QApplication
from app import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Vibration Scope')
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
