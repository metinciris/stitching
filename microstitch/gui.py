from .ui_support import *
from .ui_build import MainWindowBuildMixin
from .ui_style import MainWindowStyleMixin
from .ui_input import MainWindowInputMixin
from .ui_process import MainWindowProcessMixin


class MicroStitchStudio(
    MainWindowBuildMixin,
    MainWindowStyleMixin,
    MainWindowInputMixin,
    MainWindowProcessMixin,
    QMainWindow,
):
    pass


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("MicroStitch")
    app.setStyle("Fusion")
    window = MicroStitchStudio()
    window.show()
    return app.exec_()
