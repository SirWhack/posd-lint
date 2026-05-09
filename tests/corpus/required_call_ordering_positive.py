"""Should flag: paired lifecycle methods without context-manager protocol."""


class Connection:
    """`open` and `close` exist; no __enter__/__exit__."""

    def open(self):
        self.connected = True

    def close(self):
        self.connected = False

    def send(self, data):
        if not self.connected:
            raise RuntimeError("not open")
        return True


class Timer:
    """start_timer / stop_timer pair without a state machine."""

    def start_timer(self, name):
        self._name = name

    def stop_timer(self, name):
        self._name = None
