"""Should flag: pass-through class and shallow class."""


class Repository:
    """Real parent class."""

    def get(self, id_):
        return {"id": id_}

    def put(self, item):
        pass


class SQLiteStore(Repository):
    """Pass-through alias — adds nothing."""


class TrivialWrapper:
    """Shallow: every method is one-line."""

    def get_x(self):
        return self._x

    def get_y(self):
        return self._y

    def get_z(self):
        return self._z

    def set_x(self, x):
        self._x = x

    def set_y(self, y):
        self._y = y
