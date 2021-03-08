import errno
import os
from pathlib import Path

__all__ = ["ensure_dir_exists"]


def ensure_dir_exists(filename: Path) -> None:
    """
    Ensures the directories specified in the given path exist,
    creating them if not.

    :param filename: Path-like object whose containing directories to ensure exist.
    :raises OSError: except EEXIST
    """
    if not os.path.exists(os.path.dirname(filename)):
        try:
            os.makedirs(os.path.dirname(filename))
        except OSError as exc:  # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise
