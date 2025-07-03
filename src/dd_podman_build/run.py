import logging
import shlex
import subprocess
import threading
from datetime import datetime
from functools import cache
from io import StringIO
from typing import IO, Any, Callable

from rich.logging import RichHandler

from .console import console, log_console
from .github import github_group
from .logging import configure_logging

_Default_Kwargs: dict[str, Any] = {
    "check": True,
    "stderr": subprocess.PIPE,
    "stdout": subprocess.PIPE,
}


@cache
def make_logger(log_as: str, handle: str):
    configure_logging()

    keywords = RichHandler.KEYWORDS or []
    keywords.append(log_as)
    handler = RichHandler(
        console=log_console, show_level=False, show_path=False, keywords=keywords
    )
    prefix = f"{log_as} ⚠️" if handle == "stderr" else log_as
    handler.setFormatter(logging.Formatter(f"{prefix}: %(message)s", "[%X]"))

    logger = logging.getLogger(f"{log_as}.{handle}")
    logger.addHandler(handler)
    logger.propagate = False

    return logger


def consume_stream(stream: IO[str], consume: Callable[[str], Any]):
    [consume(line.rstrip()) for line in stream]


def emojify_returncode(returncode: int | None):
    match returncode:
        case 0:
            return "✅"
        case int():
            return "❌"
        case _:
            return "⁉️"


def run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    args = tuple(map(str, args))
    should_log_stdout = "stdout" not in kwargs
    should_log_stderr = "stderr" not in kwargs
    kwargs = {**_Default_Kwargs, **kwargs}
    check = bool(kwargs.pop("check", True))
    log_as = str(kwargs.pop("log_as", args[0]))

    if "stdin" in kwargs:
        raise Exception("stdin not supported")

    logging_threads: list[threading.Thread] = []
    captured_stdout = StringIO()
    captured_stderr = StringIO()
    start = datetime.now()
    returncode: int | None = None

    try:
        with github_group(f"🏃 {shlex.join(args)}"):
            process = subprocess.Popen(args, **kwargs, encoding="utf-8")

            if process.stdout is not None:
                logging_threads.append(
                    threading.Thread(
                        target=consume_stream,
                        args=(
                            process.stdout,
                            make_logger(log_as, "stdout").info
                            if should_log_stdout
                            else captured_stdout.write,
                        ),
                    )
                )

            if process.stderr is not None:
                logging_threads.append(
                    threading.Thread(
                        target=consume_stream,
                        args=(
                            process.stderr,
                            make_logger(log_as, "stderr").info
                            if should_log_stderr
                            else captured_stderr.write,
                        ),
                    )
                )

            [thread.start() for thread in logging_threads]
            [thread.join() for thread in logging_threads]

            while returncode is None:
                returncode = process.wait(1)
    finally:
        runtime = datetime.now() - start
        console.print(
            f"{emojify_returncode(returncode)} exit status: {returncode}, runtime: {runtime}"
        )
        console.rule()

    final_stdout = captured_stdout.getvalue() or None
    final_stderr = captured_stderr.getvalue() or None

    if check and process.returncode != 0:
        raise subprocess.CalledProcessError(
            process.returncode, args, final_stdout, final_stderr
        )

    return subprocess.CompletedProcess(
        args, process.returncode, final_stdout, final_stderr
    )
