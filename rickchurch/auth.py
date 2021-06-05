import enum
import secrets
from typing import NamedTuple, Optional, Tuple

import asyncpg
import fastapi
from fastapi.security.utils import get_authorization_scheme_param
from jose import JWTError, jwt

from rickchurch import constants


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
        if bool(self):
            return
        raise fastapi.HTTPException(status_code=403, detail=self.value)

    def raise_unless_mod(self) -> None:
        """Raise an HTTPException if a moderator isn't authorized."""
        if self == AuthState.MODERATOR:
            return
        elif self == AuthState.USER:
            raise fastapi.HTTPException(status_code=403, detail="This endpoint is limited to moderators")
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


async def authorized(authorization: Optional[str], asyncpg_conn: asyncpg.Connection) -> AuthResult:
    """Attempt to authorize the user given a token and a database connection."""
    if authorization is None:
        return AuthResult(AuthState.NO_TOKEN, None)

    scheme, token = get_authorization_scheme_param(authorization)
    if scheme.lower() != "bearer":
        return AuthResult(AuthState.BAD_HEADER, None)

    try:
        token_data = jwt.decode(token, constants.jwt_secret)
    except JWTError:
        return AuthResult(AuthState.INVALID_TOKEN, None)

    user_id = token_data["id"]
    token_salt = token_data["salt"]
    user_state = await asyncpg_conn.fetchrow(
        "SELECT is_banned, is_mod, key_salt FROM users WHERE user_id = $1;", int(user_id)
    )
    if user_state is None or user_state["key_salt"] != token_salt:
        return AuthResult(AuthState.INVALID_TOKEN, None)
    elif user_state["is_banned"]:
        return AuthResult(AuthState.BANNED, int(user_id))
    elif user_state["is_mod"]:
        return AuthResult(AuthState.MODERATOR, int(user_id))
    else:
        return AuthResult(AuthState.USER, int(user_id))


def make_user_token(user_id: int) -> Tuple[str, str]:
    """
    Generate a JWT token for given user_id.

    Returns a tuple of the JWT token, and the token_salt.
    """
    # 22 long string
    token_salt = secrets.token_urlsafe(16)
    jwt_data = dict(id=user_id, salt=token_salt)
    return jwt.encode(jwt_data, constants.jwt_secret, algorithm="HS256"), token_salt


async def reset_user_token(user_id: int, asyncpg_conn: asyncpg.Connection) -> str:
    """Regenerate the token of an existing user and invalidate the old one"""

    # Returns `None` if user doesn't exist and `False` if they aren't banned
    is_banned = await asyncpg_conn.fetchval("SELECT is_banned FROM users WHERE user_id = $1", user_id)
    if is_banned:
        raise PermissionError

    token, salt = make_user_token(user_id)

    async with asyncpg_conn.transaction():
        await asyncpg_conn.execute("UPDATE users SET key_salt=$1 WHERE user_id=$2", salt, user_id)

    return token


async def add_user(user: dict, db_conn: asyncpg.Connection) -> str:
    """
    Add a new church user. If given member already exists,
    reset his token unless he is banned.

    Return the new user's token.
    """
    user_name = f"{user['username']}#{user['discriminator']}"  # Use the username#discriminator from discord
    user_id = int(user["id"])  # User id (snowflake) from discord

    async with db_conn.transaction():
        user_data = await db_conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)

    if user_data is not None:
        # The user already exists, only reset his token
        return await reset_user_token(user_id, db_conn)

    token, salt = make_user_token(user_id)
    async with db_conn.transaction():
        # fmt: off
        await db_conn.execute(
            """INSERT INTO users (user_id, user_name, key_salt, is_mod,
            is_banned, projects_complete) VALUES ($1, $2, $3, $4, $5, $6)""",
            user_id, user_name, salt, False, False, 0
        )
        # fmt: on

    return token
