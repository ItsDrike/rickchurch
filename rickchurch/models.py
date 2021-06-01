import enum
from typing import NamedTuple, Optional

from fastapi import HTTPException


class AuthState(enum.Enum):
    """Represents possible outcomes of a user attempting to authorize."""
    NO_TOKEN = (
        "There is no token provided, provide one in an Authorization header in the format "
        "'Bearer {your token here}' or go to church's home and get one."
    )
    BAD_HEADER = "The Authorization header does not specify the Bearer scheme."
    INVALID_TOKEN = "The token provided is not a valid token or has expired."
    BANNED = "You are banned."
    MODERATOR = "This token belongs to a moderator."
    USER = "This token belongs to a regular user."

    def __bool__(self) -> bool:
        """Return whether the authorization was successful."""
        return self in (AuthState.USER, AuthState.MODERATOR)

    def raise_if_failed(self) -> None:
        """Raise an HTTPException if a user isn't authorized."""
        if self:
            return
        raise HTTPException(status_code=403, detail=self.value)

    def raise_unless_mod(self) -> None:
        """Raise an HTTPException if a moderator isn't authorized."""
        if self == AuthState.MODERATOR:
            return
        elif self == AuthState.USER:
            raise HTTPException(status_code=403, detail="This endpoint is limited to moderators")
        self.raise_if_failed()


class AuthResult(NamedTuple):
    """The possible outcomes of authorization with user id."""
    state: AuthState
    user_id: Optional[int]

    def __bool__(self) -> bool:
        """Return whether the authorization was successful"""
        return bool(self.state)

    def raise_if_failed(self) -> None:
        """Raise an HTTPException if a user isn't authorized."""
        self.state.raise_if_failed()

    def raise_unless_mod(self) -> None:
        self.state.raise_unless_mod()
