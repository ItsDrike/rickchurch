import logging
from typing import List, Tuple

import asyncpg
from httpx import AsyncClient

from rickchurch import constants
from rickchurch.models import ProjectDetails

logger = logging.getLogger("rickchurch")


async def fetch_projects(db_conn: asyncpg.Connection) -> List[ProjectDetails]:
    """Obtain list of active projects in the database"""
    async with db_conn.transaction():
        db_projects = await db_conn.fetchrow("SELECT * FROM projects")

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


async def get_oauth_user(client: AsyncClient, code: str) -> Tuple[dict, str]:
    """
    Processes the code given to us by Discord and send it back to Discord
    requesting a temporary access token so we can make requests on behalf
    (as if we were) the user. Use this to request the userinfo from
    https://discordapp.com/api/users/@me (constants.discord_user_url) and
    return the JSON data obtained.
    """
    response = await client.post(
        constants.DISCORD_BASE_URL + "/oauth2/token",
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
    response = await client.get(
        constants.DISCORD_BASE_URL + "/users/@me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    user = response.json()

    return user, access_token
