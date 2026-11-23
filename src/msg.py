def k(key, **params):
    return [key, params]


class KErr(Exception):
    k = None

    def __init__(self, text, key=None, **params):
        super().__init__(text)
        self.k = k(key, **params) if key else None


class KValueError(KErr, ValueError):
    pass


class KPermissionError(KErr, PermissionError):
    pass


def err(e):
    d = {"error": str(e)}
    if getattr(e, "k", None):
        d["error_k"] = e.k
    return d
