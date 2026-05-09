"""Should flag: generic and numbered names."""


def process(data):
    """Generic 'data' parameter."""
    result = data + 1
    return result


class Manager:
    """'Manager' is a classic vague class name."""

    def handle(self, info):
        """Vague: 'info' parameter."""
        return info


tmp = 42
data2 = "numbered generic"


def process_v2(payload):
    """Versioned function name: 'v2' says 'another one' without saying how."""
    return payload


def get_helper():
    """Adjective-only suffix: 'helper' adds nothing."""
    return 1


final_result = "differentiating-without-content prefix"
real_data = {"x": 1}


class User2:
    """CamelCase versioned class — 'User but a different one'."""
