"""Validation of the output folder below the media directory."""

from pathlib import PurePosixPath


class InvalidOutputDirError(ValueError):
    """The output folder would leave the media directory."""


def normalize_output_dir(value: str) -> str:
    """
    Return the folder as a clean relative path inside the media directory.

    Leading and trailing slashes are dropped, so "/reiseverlauf/" becomes "reiseverlauf".

    Raises:
        InvalidOutputDirError: The folder is empty or contains "..".

    """
    parts = [part for part in PurePosixPath(value.strip().replace("\\", "/")).parts if part not in {"/", "."}]
    if not parts or ".." in parts:
        raise InvalidOutputDirError(value)
    return "/".join(parts)
