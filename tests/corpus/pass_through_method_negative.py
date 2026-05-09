"""Should NOT flag: wrappers that transform args, add work, or are non-trivial."""


class Inner:
    def fetch(self, key):
        return {"key": key}


class Outer:
    def __init__(self):
        self.inner = Inner()

    def fetch_normalized(self, key):
        """Transforms the key — not a pass-through."""
        return self.inner.fetch(key.lower().strip())

    def fetch_with_log(self, key):
        """Adds logging — does real work alongside the call."""
        result = self.inner.fetch(key)
        print(f"fetched {key}")
        return result

    def fetch_with_default(self, key):
        """Adds an argument — adapter, not pass-through."""
        return self.inner.fetch(key) or {"default": True}
