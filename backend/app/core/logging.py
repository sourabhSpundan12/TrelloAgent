import logging
import re
import sys
from app.core.config import settings


class SensitiveDataFilter(logging.Filter):
    """
    Redacts sensitive credentials, API keys, tokens, and Trello parameters
    from all log records (both message templates and formatted arguments).
    """

    SENSITIVE_PATTERNS = [
        (re.compile(r'([?&]key=)[^&\s"\']+', re.IGNORECASE), r'\1[REDACTED]'),
        (re.compile(r'([?&]token=)[^&\s"\']+', re.IGNORECASE), r'\1[REDACTED]'),
        (re.compile(r'([?&]api_key=)[^&\s"\']+', re.IGNORECASE), r'\1[REDACTED]'),
        (re.compile(r'(key=)[^&\s"\']+', re.IGNORECASE), r'\1[REDACTED]'),
        (re.compile(r'(token=)[^&\s"\']+', re.IGNORECASE), r'\1[REDACTED]'),
        (re.compile(r'(Bearer\s+)[A-Za-z0-9_\-\.]+', re.IGNORECASE), r'\1[REDACTED]'),
        (re.compile(r'(AIzaSy[A-Za-z0-9_\-]{33})'), r'[REDACTED_GEMINI_KEY]'),
        (re.compile(r'(sk-[A-Za-z0-9_\-]{32,})'), r'[REDACTED_OPENAI_KEY]'),
    ]

    def _redact_str(self, text: str) -> str:
        for pattern, repl in self.SENSITIVE_PATTERNS:
            text = pattern.sub(repl, text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact_str(record.msg)

        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    self._redact_str(str(arg))
                    if isinstance(arg, (str, bytes)) or any(k in str(arg).lower() for k in ("key=", "token=", "aizasy", "sk-"))
                    else arg
                    for arg in record.args
                )
            elif isinstance(record.args, dict):
                record.args = {
                    k: self._redact_str(str(v))
                    if isinstance(v, (str, bytes)) or any(k_s in str(v).lower() for k_s in ("key=", "token=", "aizasy", "sk-"))
                    else v
                    for k, v in record.args.items()
                }
        return True


def setup_logging():
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"

    handler = logging.StreamHandler(sys.stdout)
    sensitive_filter = SensitiveDataFilter()
    handler.addFilter(sensitive_filter)

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[handler]
    )

    # Attach filter and silence/filter external loggers
    root_logger = logging.getLogger()
    root_logger.addFilter(sensitive_filter)

    for logger_name in ("httpx", "httpcore", "agentic_task_manager", "uvicorn.access"):
        log_obj = logging.getLogger(logger_name)
        log_obj.addFilter(sensitive_filter)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("motor").setLevel(logging.WARNING)


logger = logging.getLogger("agentic_task_manager")
