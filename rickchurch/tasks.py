import asyncio
import random
from functools import partial
from typing import Tuple, Union

import asyncpg
import fastapi
import pydispix

from rickchurch import constants
from rickchurch.models import ProjectDetails, Task
from rickchurch.utils import deserialize_image, postpone

# Use global variables to keep track of current task list,
# this isn't ideal, but it's the easiest solution we can use.
tasks = {}
free_tasks = []
projects = []


def submit_task(task: Task, user_id: int):
    """Try to submit a `task` from `user_id`"""
    global tasks

    if task not in tasks.values():
        raise fastapi.HTTPException(
            status_code=409,
            detail="This task doesn't exist, it was likely was already completed by someone else."
        )
    if tasks[user_id] != task:
        raise fastapi.HTTPException(
            status_code=409,
            detail="This task doesn't belong to you, "
                   "it has likely been reassigned since you took too long to complete it."
        )

    del tasks[user_id]


async def assign_free_task(user_id: int) -> Task:
    """Assign a free task to `user_id`"""
    global tasks
    global free_tasks

    if user_id in tasks:
        raise fastapi.HTTPException(status_code=409, detail="You already have a task assigned.")
    if len(free_tasks) == 0:
        raise fastapi.HTTPException(status_code=409, detail="No aviable tasks.")

    task = random.choice(free_tasks)
    free_tasks.remove(task)
    tasks[user_id] = task
    await postpone(
        constants.task_pending_delay,
        partial(unassign_task, user_id),  # type: ignore - partial doesn't explicitly return coro
        predicate=lambda: user_id in tasks
    )
    return task


def unassign_task(user_id: int):
    """Unassign given `task` from `user_id` and mark it free to be claimed"""
    global tasks
    global free_tasks

    task = tasks[user_id]
    del tasks[user_id]
    free_tasks.append(task)


async def reload_loop(db_conn: asyncpg.Connection, reload_time: Union[int, float]):
    """
    Keep continually querying the database to update the list of projects, these updates aren't
    that common, but they happen when a new project is added/removed/edited
    """
    global projects

    while True:
        db_projects = await db_conn.fetch("SELECT * FROM projects")
        for db_project in db_projects:
            project_model = ProjectDetails(
                name=db_project["project_name"],
                x=db_project["position_x"],
                y=db_project["position_y"],
                priority=db_project["priority"],
                image=db_project["base64_image"]
            )
            projects.append(project_model)

        asyncio.sleep(reload_time)


async def update_tasks(client: pydispix.Client):
    global free_tasks

    canvas = await client.get_canvas()

    local_tasks = []
    for project in projects:
        img = deserialize_image(project.image)

        img_rgb = img.convert("RGB")
        w, h = img.size

        random_pixels = list(range(w * h))
        random.shuffle(random_pixels)  # this happens in-place

        for pixel_no in random_pixels:
            x = pixel_no % w
            y = pixel_no // w
            color: Tuple[int, int, int] = img_rgb.getpixel((x, y))  # type: ignore - this is RGB (3x int tuple)

            # Check if color is already matching
            if canvas[x, y].triple == color:
                continue

            local_tasks.append(Task(x=x, y=y, rgb=pydispix.parse_color(color)))

    active_tasks = set(free_tasks).union(set(tasks.values()))
    for task in local_tasks:
        if task in active_tasks:
            continue
        free_tasks.append(task)
