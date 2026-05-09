"""Should flag: methods that just forward to a delegate."""


class Inner:
    def fetch(self, key):
        return {"key": key}

    def store(self, key, value):
        return True


class Outer:
    def __init__(self):
        self.inner = Inner()

    def fetch(self, key):
        return self.inner.fetch(key)  # textbook pass-through

    def store(self, key, value):
        return self.inner.store(key, value)  # textbook pass-through

    def fetch_async(self, key):
        return self.inner.fetch(key)  # name differs but still pure forward
