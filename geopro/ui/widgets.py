from PyQt5.QtWidgets import QApplication, QPushButton, QHBoxLayout, QLabel, QWidget, QSizePolicy
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt, QSize

class IconTextButton(QPushButton):
    def __init__(self, icon: QIcon, text: str, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # self.setFlat(True)  # optional: makes it cleaner

        # # Clear default text/icon
        # super().setText("")
        # super().setIcon(QIcon())

        # Layout inside the button
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)  # padding
        layout.setSpacing(0)

        # Icon label
        self.icon_label = QLabel()
        self.icon_label.setPixmap(icon.pixmap(QSize(18, 18)))
        layout.addWidget(self.icon_label, alignment=Qt.AlignLeft)

        # Text label
        self.text_label = QLabel(text)
        self.text_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.text_label, stretch=1)

        self.setMinimumHeight(28)

