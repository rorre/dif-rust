import functools
import os
from pathlib import Path
from typing import Set

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QDoubleValidator
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from dif.finder import FileDuplicates, find_duplicates, get_all_images, get_hashes


def isValidFolder(folder):
    return os.path.exists(folder) and os.path.isdir(folder)


class DuplicateWorker(QThread):
    """Worker for duplicate finder.

    It is run on another thread so that it does not block the UI thread."""

    # We track the progress count on a private variable.
    _progress = 0
    progress = pyqtSignal(int)
    totalImages = pyqtSignal(int)
    duplicateImages = pyqtSignal(dict)

    def __init__(self, folder: str, hashSize: int, threshold: float, *args, **kwargs):
        self._folder = folder
        self._hashSize = hashSize
        self._threshold = threshold
        super().__init__(*args, **kwargs)

    def _updateProgress(self):
        """Updates the progress of worker and emits to signal."""
        self._progress += 1
        self.progress.emit(self._progress)

    def run(self):
        imagePaths = get_all_images(self._folder)
        self.totalImages.emit(len(imagePaths))

        hashes = get_hashes(
            imagePaths,
            self._hashSize,
            increment_func=self._updateProgress,
        )
        self._progress = 0
        self.progress.emit(0)

        self.duplicateImages.emit(
            find_duplicates(
                imagePaths,
                hashes,
                self._hashSize,
                (1 - self._threshold),
                increment_func=self._updateProgress,
            )
        )


class ImagePopup(QWidget):
    def __init__(self, imagePixmap: QPixmap, text=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.imagePixmap = imagePixmap
        self.imw, self.imh = self.imagePixmap.width(), self.imagePixmap.height()

        self.imageLabel = QLabel(self)
        self.imageLabel.setPixmap(self.imagePixmap)

        # Align to top so that upon resize the image doesnt get drown out of window.
        self.imageLabel.setAlignment(Qt.AlignmentFlag(Qt.AlignTop | Qt.AlignHCenter))

        if text:
            self.setWindowTitle(text)
        else:
            self.setWindowTitle("View Image")

    def resizeEvent(self, _):
        # Upon resize, we want the entire image to still be visible in the window,
        # so we resize it while keeping its aspect ratio.
        w, h = self.width(), self.height()

        # This is ultimately way too complicated, but it's purpose is to
        # scale the image based on the window's height.
        scaleDenominator = self.imh // h
        scaledWidth = self.imw // scaleDenominator
        resizedPixmap = self.imagePixmap.scaled(
            scaledWidth, h, Qt.AspectRatioMode.KeepAspectRatio
        )
        self.imageLabel.setPixmap(resizedPixmap)
        self.imageLabel.setGeometry(0, 0, w, h)


class QImageLabel(QLabel):
    def __init__(self, imagePath: str, w: int, h: int, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.imagePath = imagePath
        self.imagePixmap = QPixmap(imagePath)
        self.setPixmap(self.imagePixmap.scaled(w, h, Qt.KeepAspectRatio))

    def mousePressEvent(self, ev):
        self.popup = ImagePopup(self.imagePixmap, text=f"Image {self.imagePath}")

        w, h = self.imagePixmap.width(), self.imagePixmap.height()
        self.popup.setGeometry(0, 0, w, h)
        self.popup.show()


class QImageMarker(QCheckBox):
    """Wrapper around QCheckBox to give imagePath data."""

    def __init__(self, imagePath: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.imagePath = imagePath


class Window(QMainWindow):
    """Main Window."""

    runningThread = None
    markedData: Set[str] = set()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Duplicate Image Finder")

        # Create all the necessary layout and widgets.
        self.createSensitivityRow()
        self.createFolderSelect()
        self.createProgressBar()
        self.createDuplicateImageArea()

        deleteButton = QPushButton("Delete marked")
        deleteButton.clicked.connect(self._startDelete)

        # After that, put all of them in our main layout.
        mainLayout = QGridLayout()
        mainLayout.addLayout(self.folderLayout, 0, 0)
        mainLayout.addWidget(self.progressBar, 1, 0)
        mainLayout.addLayout(self.sensitivityLayout, 2, 0)
        mainLayout.addWidget(self.imagesScrollArea, 3, 0)
        mainLayout.addWidget(deleteButton, 4, 0)

        # QMainWindow cannot have layout as its central widget, so we wrap the layout
        # into a QWidget, then use it as our central widget.
        window = QWidget()
        window.setLayout(mainLayout)

        self.setCentralWidget(window)
        self.setMinimumSize(800, 600)

    def _startDelete(self):
        if not self.markedData:
            QMessageBox.information(
                self,
                "Information",
                "You do not have any images marked.",
            )
            return

        deletePopup = QMessageBox(self)
        deletePopup.setText("Are you sure you want to delete these files?")
        deletePopup.setInformativeText("\r\n".join(self.markedData))
        deletePopup.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        deletePopup.setIcon(QMessageBox.Information)
        pickedOption = deletePopup.exec()

        totalImages = len(self.markedData)
        if pickedOption == QMessageBox.Yes:
            self.progressBar.reset()
            self.progressBar.setMaximum(totalImages)
            self.progressBar.setValue(0)

            for i, imagePath in enumerate(self.markedData):
                Path(imagePath).unlink(missing_ok=True)
                self.progressBar.setValue(i + 1)

            QMessageBox.information(
                self,
                "Deletion Successful",
                f"Successfully deleted {totalImages} images.",
            )

            self._cleanupDuplicateArea()
            self.imagesLayout.addWidget(
                QLabel("Deleted {totalImages} images."),
                alignment=Qt.AlignCenter,
            )
            self.progressBar.reset()

    def _getFolderAndExecute(self):
        # Reset the progress bar before executing, this is crucial as we don't want
        # previous execution result to stick while we work on the new one.
        self.progressBar.reset()

        targetFolder = QFileDialog.getExistingDirectory(caption="Select Folder...")
        self.folderPathWidget.setText(targetFolder)

        if not targetFolder:
            return

        if not isValidFolder(targetFolder):
            QMessageBox.critical(self, "Error", "Folder not found.")
            return

        self._cleanupDuplicateArea()
        self.imagesLayout.addWidget(
            QLabel("Finding duplicate images..."),
            alignment=Qt.AlignCenter,
        )

        threshold = float(self.thresholdWidget.text())
        hashSize = int(self.hashSizeDropdown.currentText())

        self.runningThread = DuplicateWorker(targetFolder, hashSize, threshold)
        self.runningThread.totalImages.connect(self.progressBar.setMaximum)
        self.runningThread.progress.connect(self.progressBar.setValue)
        self.runningThread.duplicateImages.connect(self.showDuplicateImages)
        self.runningThread.start()

    def _updateSelection(self, _):
        checkBox: QImageMarker = self.sender()
        if checkBox.isChecked():
            self.markedData.add(checkBox.imagePath)
        else:
            self.markedData.discard(checkBox.imagePath)

    def _cleanupDuplicateArea(self):
        layout = self.imagesLayout
        for i in reversed(range(layout.count())):
            layout.itemAt(i).widget().setParent(None)

    def showDuplicateImages(self, duplicates: FileDuplicates):
        """Show all result from duplicate image worker.

        This is running in the same thread as UI, so on big result we might experience lag."""
        # Clean up previous result before proceeding.
        self._cleanupDuplicateArea()

        # Skip if no duplicate image is found.
        if not duplicates:
            self.imagesLayout.addWidget(
                QLabel("No duplicate images found."),
                alignment=Qt.AlignCenter,
            )
            self.progressBar.reset()
            return

        total = functools.reduce(lambda x, y: x + len(y), duplicates.values(), 0)
        total += len(duplicates)

        if total > 100:
            result = QMessageBox.warning(
                self,
                "Big result size",
                f"There is a lot of images detected for duplicate ({total}), are you sure to show them?",
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Ok,
            )

            if result != QMessageBox.Ok:
                self.imagesLayout.addWidget(
                    QLabel("Cancelled."),
                    alignment=Qt.AlignCenter,
                )
                self.progressBar.reset()
                return

        for hashName, fileNames in duplicates.items():
            imageFrame = QGroupBox(hashName)
            imageFrameLayout = QHBoxLayout()

            for f in fileNames:
                divisor = len(fileNames) + 1
                w, h = (
                    self.imagesScrollArea.width() // divisor,
                    self.imagesScrollArea.height() // divisor,
                )

                picLayout = QVBoxLayout()
                picLayout.setAlignment(Qt.AlignCenter)

                # Image + resolution label
                picLabel = QImageLabel(str(f), w, h)
                w, h = picLabel.imagePixmap.width(), picLabel.imagePixmap.height()
                resoLabel = QLabel(f"{w}x{h}")
                resoLabel.setAlignment(Qt.AlignHCenter)

                # Deletion checkbox
                picCheckbox = QImageMarker(str(f), "Mark for deletion")
                picCheckbox.stateChanged.connect(self._updateSelection)

                picLayout.addWidget(picLabel)
                picLayout.addWidget(resoLabel)
                picLayout.addWidget(picCheckbox)

                imageFrameLayout.addLayout(picLayout)

            imageFrame.setLayout(imageFrameLayout)
            self.imagesLayout.addWidget(imageFrame)

    def createSensitivityRow(self):
        hashSizeLabel = QLabel("Hash size:")
        thresholdLabel = QLabel("Threshold:")

        self.hashSizeDropdown = QComboBox()
        self.hashSizeDropdown.addItems(["8", "16", "32", "64"])

        validator = QDoubleValidator(0.0, 1.0, 2)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.thresholdWidget = QLineEdit("0.8")
        self.thresholdWidget.setValidator(validator)

        self.sensitivityLayout = QHBoxLayout()
        self.sensitivityLayout.addWidget(hashSizeLabel)
        self.sensitivityLayout.addWidget(self.hashSizeDropdown)
        self.sensitivityLayout.addWidget(thresholdLabel)
        self.sensitivityLayout.addWidget(self.thresholdWidget)

    def createFolderSelect(self):
        """Creates the folder selection layout."""
        folderWidgetLabel = QLabel("Working folder:")
        self.folderPathWidget = QLineEdit()
        self.folderPathWidget.setReadOnly(True)
        folderSelectButton = QPushButton("Browse")
        folderSelectButton.clicked.connect(self._getFolderAndExecute)

        self.folderLayout = QHBoxLayout()
        self.folderLayout.addWidget(folderWidgetLabel)
        self.folderLayout.addWidget(self.folderPathWidget)
        self.folderLayout.addWidget(folderSelectButton)

    def createProgressBar(self):
        """Creates and configures the progress bar."""
        self.progressBar = QProgressBar()
        self.progressBar.setTextVisible(True)
        self.progressBar.setFormat("%p% (%v/%m)")

    def createDuplicateImageArea(self):
        """Creates duplicate image result area."""
        self.imagesScrollArea = QScrollArea()
        self.imagesScrollArea.setWidgetResizable(True)

        self.widget = QWidget()
        self.imagesLayout = QVBoxLayout()

        self.imagesLayout.addWidget(QLabel("Empty..."), alignment=Qt.AlignCenter)
        self.widget.setLayout(self.imagesLayout)
        self.imagesScrollArea.setWidget(self.widget)


def run(args):
    app = QApplication(args)
    # apply_stylesheet(app, theme="dark_blue.xml")
    win = Window()
    win.show()
    app.exec_()
