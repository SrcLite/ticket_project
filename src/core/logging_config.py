import logging
import sys
from pythonjsonlogger import jsonlogger

def setup_logging():
    log_handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    log_handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.handlers = [log_handler]
    root_logger.setLevel(logging.INFO)

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)