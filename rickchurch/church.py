import logging
from rickchurch.models import AuthResult, AuthState
from fastapi.security.utils import get_authorization_scheme_param
from typing import Optional
from jose import JWTError, jwt
import asyncpg

import pydispix
from fastapi import FastAPI

from rickchurch import constants

logger = logging.getLogger(__name__)
app = FastAPI()
client: Optional[pydispix.Client] = None
canvas: Optional[pydispix.Canvas] = None


@app.on_event("startup")
async def startup() -> None:
    # We have to make a global client and canvas objects as there is no way for
    # us to send the objects to the following requests from this function.
    global client
    global canvas
    client = pydispix.Client(constants.pixels_api_token)
    canvas = await client.get_canvas()


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
