import asyncio
import base64
import inspect
import logging
from io import BytesIO
from typing import Callable, Coroutine, List, Tuple, Union

import PIL.Image
import asyncpg
import httpx

from rickchurch import constants
from rickchurch.models import ProjectDetails

logger = logging.getLogger("rickchurch")


async def fetch_projects(db_conn: asyncpg.Connection) -> List[ProjectDetails]:
    """Obtain list of active projects in the database"""
    async with db_conn.transaction():
        db_projects = await db_conn.fetch("SELECT * FROM projects")

    projects = []
    for db_project in db_projects:
        project = ProjectDetails(
            name=db_project["project_name"],
            x=db_project["position_x"],
            y=db_project["position_y"],
            priority=db_project["project_priority"],
            image=db_project["base64_image"],
        )
        projects.append(project)
    return projects


async def get_oauth_user(httpx_client: httpx.AsyncClient, code: str) -> Tuple[dict, str]:
    """
    Processes the code given to us by Discord and send it back to Discord
    requesting a temporary access token so we can make requests on behalf
    (as if we were) the user. Use this to request the userinfo from
    https://discordapp.com/api/users/@me (constants.discord_user_url) and
    return the JSON data obtained together with the user access token.
    """
    response = await httpx_client.post(
        f"{constants.DISCORD_BASE_URL}/oauth2/token",
        data=dict(
            client_id=constants.client_id,
            client_secret=constants.client_secret,
            grant_type="authorization_code",
            code=code,
            redirect_uri=f"{constants.base_url}/oauth_callback",
            scope="identify",
        ),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    data = response.json()
    try:
        access_token = data["access_token"]
    except KeyError as exc:
        logger.error(f"Unable to obtain access token (response: {data})")
        raise exc
    response = await httpx_client.get(
        f"{constants.DISCORD_BASE_URL}/users/@me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    user = response.json()

    return user, access_token


def deserialize_image(base64_string: str) -> PIL.Image.Image:
    """Convert serialized base64 image string to an actual image"""
    return PIL.Image.open(BytesIO(base64.b64decode(base64_string)))


def serialize_image(image: PIL.Image.Image) -> str:
    """Convert an actual image into deserialized base64 string"""
    f = BytesIO()
    image.save(f, format="PNG")
    return base64.b64encode(f.getvalue()).decode()


async def postpone(seconds: Union[int, float], coro: Coroutine, predicate: Callable):
    try:
        await asyncio.sleep(seconds)
        if predicate is True:
            # Prevent `coro` from cancelling itself by shielding it
            await asyncio.shield(coro)
    finally:
        # Prevent coroutine never awaited error if it got cancelled during sleep
        # But only do so if it wasn't awaited yet, since the coro can also cancel itself
        if inspect.getcoroutinestate(coro) == "CORO_CREATED":
            coro.close()
