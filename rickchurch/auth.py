import secrets
from typing import Optional

import asyncpg
from fastapi.security.utils import get_authorization_scheme_param
from jose import JWTError, jwt

from rickchurch import constants
from rickchurch.models import AuthResult, AuthState


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
        "SELECT is_banned, is_mod, key_salt, FROM users WHERE user_id = $1;", int(user_id)
    )
    if user_state is None or user_state["key_salt"] != token_salt:
        return AuthResult(AuthState.INVALID_TOKEN, None)
    elif user_state["is_banned"]:
        return AuthResult(AuthState.BANNED, int(user_id))
    elif user_state["is_mod"]:
        return AuthResult(AuthState.MODERATOR, int(user_id))
    else:
        return AuthResult(AuthState.USER, int(user_id))


async def reset_user_token(user_id: int, asyncpg_conn: asyncpg.Connection) -> str:
    """
    Ensure a user exists and create a new token for them.

    If the user already exists, their token is regenerated and the old token is invalidated.
    """
    # Returns `None` if user doesn't exist and `False` if they aren't banned
    is_banned = await asyncpg_conn.fetchval("SELECT is_banned FROM users WHERE user_id = $1", user_id)
    if is_banned:
        raise PermissionError

    # 22 long string
    token_salt = secrets.token_urlsafe(16)
    is_mod = user_id in constants.mods
    async with asyncpg_conn.transaction():
        await asyncpg_conn.execute(
            """INSERT INTO users (user_id, key_salt, is_mod) VALUES ($1, $1, $3)
            ON CONFLICT (user_id) DO UPDATE SET key_salt=$2""",
            user_id, token_salt, is_mod
        )
    jwt_data = dict(id=user_id, salt=token_salt)
    return jwt.encode(jwt_data, constants.jwt_secret, algorithm="HS256")