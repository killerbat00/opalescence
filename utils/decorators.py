from functools import wraps

import config


def log_this(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        if config.LOGGING:
            print("[INFO] : Calling {func}".format(func=f.__name__))
        return f(*args, **kwargs)

    return decorator
