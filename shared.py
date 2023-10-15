
import loguru
from loguru._logger import Logger
import sys
import os
from dotenv import load_dotenv


load_dotenv()
log_file = os.environ.get("LOG_FILE", sys.stderr)
log_level = os.environ.get("LOG_LEVEL", "INFO")
assert os.environ.get("LOG_LEVEL") in [
    "TRACE",
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
], "Invalid log level specified"

logger = None


def get_logger() -> Logger:
    if logger is None:
        log = loguru.logger
        log.remove()
        log.add(log_file, level=log_level)
        return log
    return logger


logger = get_logger()
