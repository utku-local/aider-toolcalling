"""Hidden check for the large-file task.
It calls all forty handlers and compares each one's policy, log level and validation with the expected table.
Exit code 0 means the task passed.
"""

import logging

import handlers

DOMAINS = ("user", "payment", "order", "inventory", "email")
ACTIONS = ("create", "update", "delete", "refund", "capture", "cancel", "sync", "archive")
TIMEOUTS = {"inventory.sync": 120, "payment.refund": 45}
RETRIES = {"email.create": 1, "payment.capture": 5}
DEFAULT_TIMEOUT, DEFAULT_RETRIES = 30, 3


class Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


capture = Capture()
handlers.logger.addHandler(capture)
handlers.logger.setLevel(logging.DEBUG)
assert len(handlers.HANDLERS) == len(DOMAINS) * len(ACTIONS)

for domain in DOMAINS:
    for action in ACTIONS:
        event = f"{domain}.{action}"
        function = getattr(handlers, f"handle_{domain}_{action}")
        assert handlers.HANDLERS[event] is function, event
        capture.records.clear()
        result = function({"id": 7, "reason": "r"})
        assert result["event"] == event and result["id"] == 7, result
        policy = result["policy"]
        assert policy.timeout_s == TIMEOUTS.get(event, DEFAULT_TIMEOUT), (event, policy)
        assert policy.retries == RETRIES.get(event, DEFAULT_RETRIES), (event, policy)
        assert len(capture.records) == 1, (event, len(capture.records))
        record = capture.records[0]
        assert record.getMessage() == f"{event} received", record.getMessage()
        assert record.levelno == (logging.DEBUG if domain == "user" else logging.INFO), (event, record.levelname)
        try:
            function({})
        except handlers.HandlerError as err:
            assert str(err) == f"{event}: missing id", str(err)
        else:
            raise AssertionError(f"{event}: no error without id")
        if event == "order.cancel":
            try:
                function({"id": 7})
            except handlers.HandlerError as err:
                assert str(err) == "order.cancel: missing reason", str(err)
            else:
                raise AssertionError("order.cancel accepted a payload without a reason")
        else:
            assert function({"id": 7})["id"] == 7
