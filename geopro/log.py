import logging
import sys
import colorlog

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QTextEdit


def setup_logging(logger_name):
    log = logging.getLogger(logger_name)

    if not log.handlers:  # ← CRITICAL
        handler = logging.StreamHandler(sys.stdout)
        formatter = colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s [%(levelname)s] %(message)s",
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        )
        handler.setFormatter(formatter)
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False

    log.propagate = False
    return log

def setup_add_logger(log, additional_logger_name, new_level=logging.WARNING):
    log_wdm = logging.getLogger(additional_logger_name)
    log_wdm.setLevel(new_level)
    for handler_i in log.handlers:
        log_wdm.addHandler(handler_i)

class QtLogEmitter(QObject):
    log_signal = pyqtSignal(str)


class QtColorLogHandler(logging.Handler):
    """
    Logging handler that emits HTML-colored log messages to Qt.
    """

    COLOR_MAP = {
        "DEBUG": "#9CDCFE",
        "INFO": "#D4D4D4",
        "WARNING": "#D7BA7D",
        "ERROR": "#F44747",
        "CRITICAL": "#FF0000",
    }

    def __init__(self, emitter: QtLogEmitter):
        super().__init__()
        self.emitter = emitter

    def emit(self, record):
        level = record.levelname
        color = self.COLOR_MAP.get(level, "#FFFFFF")

        msg = self.format(record)
        html = f'<span style="color:{color}">{msg}</span>'

        self.emitter.log_signal.emit(html)


class QLogger:
    def init_ui_logging(self, log, log_level=logging.INFO):
        # Create a textbox for log output
        self.textbox_log = QTextEdit()
        self.textbox_log.setReadOnly(True)
        self.textbox_log.setAcceptRichText(True)
        self.textbox_log.setVisible(False)

        log.debug("Configuring GUI logging")

        self.log_emitter = QtLogEmitter()
        self.log_emitter.log_signal.connect(self._append_log)

        handler = QtColorLogHandler(self.log_emitter)

        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.setLevel(log_level)

        log.addHandler(handler)

    def _append_log(self, html: str):
        self.textbox_log.append(html)