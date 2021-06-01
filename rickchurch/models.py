import re

import pydantic

_RGB_RE = re.compile(r"[0-9a-fA-F]{6}")


class Task(pydantic.BaseModel):
    """A task used by the API."""
    x: int
    y: int
    rgb: str

    # Validators for x and y aren't added, because we don't know canvas dimensions
    # and we can't make async request for them here, so we only validate rgb
    @pydantic.validator("rgb")
    def rgb_must_be_valid_hex(cls, rgb: str) -> str:  # noqa: N805 - method argument should be self
        """Ensure rgb is a 6 characters long hexadecimal string."""
        if _RGB_RE.fullmatch(rgb):
            return rgb
        else:
            raise ValueError(
                f"{rgb!r} is not a valid color, "
                "please use the hexadecimal format RRGGBB, "
                "for example FF00ff for purple."
            )


class Project(pydantic.BaseModel):
    """A project used by the API."""
    name: str
    x: int
    y: int
    priority: int
    image: str  # base64 encoded image string
