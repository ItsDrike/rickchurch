import base64
import binascii
import re
from io import BytesIO

import pydantic
import PIL
import PIL.Image

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

    def __hash__(self):
        # Make sure same tasks have the same hash, for easy O(1) lookups
        return hash((self.x, self.y, self.rgb))


class ProjectDetails(pydantic.BaseModel):
    """A project used by the API."""

    name: str
    x: int
    y: int
    priority: int
    image: str

    @pydantic.validator("image")
    def image_must_be_base64_img(cls, image: str) -> str:   # noqa: N805 - method argument should be self
        try:
            decoded = base64.b64decode(image)
            _ = PIL.Image.open(BytesIO(decoded))
            return image
        except binascii.Error:
            raise ValueError("image must be base64 encoded image")
        except PIL.UnidentifiedImageError:
            raise ValueError("image must be PNG encoded with base64")


class Project(pydantic.BaseModel):
    """Identifiable project. Name is all we need to find any project."""

    name: str


class User(pydantic.BaseModel):
    """A user as used by the API."""

    user_id: int

    @pydantic.validator("user_id")
    def user_id_must_be_snowflake(cls, user_id: int) -> int:  # noqa: N805 - method argument should be self
        """Ensure the user_id is a valid discord snowflake."""
        if user_id.bit_length() <= 63:
            return user_id
        else:
            raise ValueError("user_id must fit within a 64 bit int.")


class Message(pydantic.BaseModel):
    """An API response message."""

    message: str
