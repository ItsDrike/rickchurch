import logging
import os
import sys

import colorama


class ColoredFormatter(logging.Formatter):
    COLORS = {
        "WARNING": colorama.Fore.YELLOW,
        "INFO": colorama.Fore.WHITE,
        "DEBUG": colorama.Fore.BLUE,
        "CRITICAL": f"{colorama.Style.BRIGHT}{colorama.Fore.RED}",
        "ERROR": f"{colorama.Style.DIM}{colorama.Fore.RED}",
    }
    RESET_SEQ = f"{colorama.Style.RESET_ALL}{colorama.Fore.RESET}"

    def __init__(self, fmt: str, *args, use_color: bool = True, **kwargs) -> None:
        super().__init__(fmt, *args, **kwargs)
        self.use_color = use_color

    def format(self, record: logging.LogRecord):
        levelname = record.levelname
        if self.use_color and levelname in self.COLORS:
            levelname_color = self.COLORS[levelname] + levelname + self.RESET_SEQ
            record.levelname = levelname_color
        return super().format(record)


def setup_logging():
    debug_mode = 'DEBUG' in os.environ
    log_format = ColoredFormatter(
        f"{colorama.Fore.GREEN}%(asctime)s {colorama.Fore.RESET} | "
        f"{colorama.Style.BRIGHT} %(name)s {colorama.Style.RESET_ALL}   | "
        "%(levelname)s  | %(message)s"
    )
    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setFormatter(log_format)

    logger = logging.getLogger("pydispix")
    logger.setLevel(logging.DEBUG if debug_mode else logging.INFO)
    logger.addHandler(stream_handler)
