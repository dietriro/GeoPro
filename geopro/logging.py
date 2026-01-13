import logging
import sys
import colorlog


def setup_logging():
    log = logging.getLogger("geopro")

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

def setup_add_logger(add_logger_name, new_level=logging.WARNING):
    log = logging.getLogger("geopro")

    log_wdm = logging.getLogger('WDM')
    log_wdm.setLevel(new_level)
    for handler_i in log.handlers:
        log_wdm.addHandler(handler_i)