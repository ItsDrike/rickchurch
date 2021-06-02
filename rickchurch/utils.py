from typing import List

import asyncpg
import httpx

from rickchurch import constants
from rickchurch.models import Project


async def fetch_projects(db_conn: asyncpg.Connection) -> List[Project]:
    """Obtain list of active projects in the database"""
    async with db_conn.transaction():
        db_projects = await db_conn.fetchrow("SELECT * FROM projects")

    projects = []
    for db_project in db_projects:
        project = Project(
            name=db_project["project_name"],
            x=db_project["position_x"],
            y=db_project["position_y"],
            priority=db_project["project_priority"],
            image=db_project["base64_image"]
        )
        projects.append(project)
    return projects


async def get_oauth_user(code: str) -> dict:
    """
    Processes the code given to us by Discord and send it back to Discord
    requesting a temporary access token so we can make requests on behalf
    (as if we were) the user. Use this to request the userinfo from
    https://discordapp.com/api/users/@me (constants.discord_user_url) and
    return the JSON data obtained.
    """
    params = dict(
        client_id=constants.client_id,
        client_secret=constants.client_secret,
        grant_type="authorization_code",
        code=code,
        redirect_uri=f"{constants.base_url}/oauth_callback",
        scope="identify",
    )
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    async with httpx.AsyncClient() as client:
        response = await client.post(constants.discord_token_url, data=params, headers=headers)
        discord_token = response.json()
        auth_header = {"Authorization": f"Bearer {discord_token['access_token']}"}
        response = await client.get(constants.discord_user_url, headers=auth_header)
        user = response.json()

    return user
