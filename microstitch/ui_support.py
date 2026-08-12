from .pipeline import *

import traceback
import subprocess

try:
    from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QUrl
    from PyQt5.QtGui import QIcon, QPixmap, QImage, QPainter, QDesktopServices
    from PyQt5.QtWidgets import (
        QApplication,
        QMainWindow,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QGridLayout,
        QFormLayout,
        QLabel,
        QPushButton,
        QListWidget,
        QListWidgetItem,
        QFileDialog,
        QLineEdit,
        QProgressBar,
        QTabWidget,
        QGroupBox,
        QComboBox,
        QCheckBox,
        QSpinBox,
        QDoubleSpinBox,
        QTextEdit,
        QMessageBox,
        QSplitter,
        QGraphicsView,
        QGraphicsScene,
        QGraphicsPixmapItem,
        QFrame,
        QAbstractItemView,
    )
except Exception as exc:
    raise SystemExit(
        "PyQt5 is required for the graphical interface.\n"
        "Install dependencies with:\n"
        "pip install opencv-contrib-python numpy scipy tifffile PyQt5\n\n"
        f"Original error: {exc}"
    )


APP_NAME = "MicroStitch Studio"
APP_VERSION = "1.1"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


class CancelledError(RuntimeError):
    pass


class ImageListWidget(QListWidget):
    filesDropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setIconSize(QSize(58, 58))
        self.setSpacing(4)
        self.setAlternatingRowColors(False)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        paths = []
        for url in event.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.is_dir():
                for child in sorted(p.iterdir()):
                    if child.suffix.lower() in IMAGE_EXTENSIONS:
                        paths.append(str(child))
            elif p.suffix.lower() in IMAGE_EXTENSIONS:
                paths.append(str(p))
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class ZoomableImageView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setFrameShape(QFrame.NoFrame)
        self._has_image = False

    def set_image(self, path):
        pixmap = QPixmap(path)
        if pixmap.isNull():
            self.clear_image()
            return False
        self.pixmap_item.setPixmap(pixmap)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())
        self._has_image = True
        self.fit_to_window()
        return True

    def clear_image(self):
        self.pixmap_item.setPixmap(QPixmap())
        self._has_image = False
        self.scene.setSceneRect(0, 0, 1, 1)

    def fit_to_window(self):
        if self._has_image:
            self.resetTransform()
            self.fitInView(self.pixmap_item, Qt.KeepAspectRatio)

    def wheelEvent(self, event):
        if not self._has_image:
            return super().wheelEvent(event)
        factor = 1.20 if event.angleDelta().y() > 0 else 1 / 1.20
        current = self.transform().m11()
        target = current * factor
        if 0.03 <= target <= 40.0:
            self.scale(factor, factor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._has_image and self.transform().m11() < 0.10:
            self.fit_to_window()


class StitchWorker(QThread):
    progressSignal = pyqtSignal(str, float, str)
    finishedSignal = pyqtSignal(object)
    failedSignal = pyqtSignal(str)

    def __init__(self, paths, output_dir, settings, parent=None):
        super().__init__(parent)
        self.paths = list(paths)
        self.output_dir = str(output_dir)
        self.settings = settings
        self.cancel_requested = False

    def request_cancel(self):
        self.cancel_requested = True

    def _progress(self, stage, fraction, message):
        if self.cancel_requested:
            raise CancelledError("Operation cancelled by user.")
        self.progressSignal.emit(str(stage), float(fraction), str(message))

    def run(self):
        try:
            report = run_pipeline(
                paths=self.paths,
                output_dir=self.output_dir,
                settings=self.settings,
                progress=self._progress,
            )
            if self.cancel_requested:
                raise CancelledError("Operation cancelled by user.")
            self.finishedSignal.emit(report)
        except CancelledError as exc:
            self.failedSignal.emit(str(exc))
        except Exception:
            self.failedSignal.emit(traceback.format_exc())


class MetricCard(QFrame):
    def __init__(self, title, value="-", parent=None):
        super().__init__(parent)
        self.setObjectName("metricCard")
        self.setMinimumHeight(76)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)
        self.title = QLabel(title)
        self.title.setObjectName("metricTitle")
        self.value = QLabel(value)
        self.value.setObjectName("metricValue")
        layout.addWidget(self.title)
        layout.addWidget(self.value)

    def set_value(self, text):
        self.value.setText(str(text))
