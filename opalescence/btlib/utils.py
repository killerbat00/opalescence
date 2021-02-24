import errno
import os
from pathlib import Path

__all__ = ["ensure_dir_exists"]


def ensure_dir_exists(filename: Path):
    if not os.path.exists(os.path.dirname(filename)):
        try:
            os.makedirs(os.path.dirname(filename))
        except OSError as exc:  # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise
