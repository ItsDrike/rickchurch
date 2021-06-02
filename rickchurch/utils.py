from typing import List

import asyncpg


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
