import json
import logging
import sys


class JsonFormatter(logging.Formatter):
    _extra = ("request_id", "method", "path", "status", "duration_ms", "analysis_id", "provider", "latency_ms", "outcome")

    def format(self, record: logging.LogRecord) -> str:
        data = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"), "level": record.levelname,
                "logger": record.name, "msg": record.getMessage()}
        for k in self._extra:
            if hasattr(record, k):
                data[k] = getattr(record, k)
        if record.exc_info and record.exc_info[0]:
            data["exc_type"] = record.exc_info[0].__name__  # type only: messages may contain user data
        return json.dumps(data)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    # httpx logs full request URLs at INFO, and our providers pass API keys as query parameters.
    for noisy in ("httpx", "httpcore", "hpack"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
