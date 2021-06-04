import asyncio
import random
import time
from functools import partial
from typing import Optional, Tuple

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
canvas: Optional[pydispix.Canvas] = None
update_time = float("-inf")  # Unix last update timestamp


async def submit_task(task: Task, user_id: int) -> None:
    """Try to submit a `task` from `user_id`, raise 409 on fail."""
    global tasks

    submit_time = time.time()

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

    pixel = await get_fastest_pixel(task.x, task.y, submit_time)
    pixel_color = pydispix.parse_color(pixel)
    if pixel_color != task.rgb:
        raise fastapi.HTTPException(
            status_code=409,
            detail="Validation error, you didn't actually complete this task"
        )

    del tasks[user_id]


async def get_fastest_pixel(x: int, y: int, submit_time: float) -> pydispix.Pixel:
    """
    Get pixel at `x, y` in the fastest possible way.
    This pixel needs to have been fetched after `submit_time`.

    - If the canvas already got updated, simply return the pixel from it.
    - If the wait time on `get_pixel` would be lower than the wait time to
    re-update the canvas, use `get_pixel` endpoint instead.
    - If both of the above are false, wait out the time limit to canvas update.
    """
    if update_time >= submit_time:
        return canvas[x, y]
    else:
        # We haven't yet updated the canvas
        expected_update_time = constants.task_refresh_time + update_time
        # TODO: Set a minimum time difference to bother with get_pixel,
        # we can just wait it out if it's not too long

        # Check if expected time for use get_pixel endpoint wouldn't be lower
        url = constants.CLIENT.resolve_endpoint("/get_pixel")
        # TODO: Waiting on pydispix update, make_raw_request needs to use httpx/async
        constants.CLIENT.make_raw_request(
            "HEAD", url,
            headers=constants.CLIENT.headers,
            update_rate_limits=True
        )
        wait_time = constants.CLIENT.rate_limiter.rate_limits[url].get_wait_time()
        expected_get_pixel_time = wait_time + time.time()

        if expected_update_time > expected_get_pixel_time:
            # Using get_pixel will be faster than waiting for canvas update
            return await constants.CLIENT.get_pixel(x, y)

    # Waiting for get_pixel would take longer, wait out the canvas update
    wait_time = expected_update_time - time.time()
    await asyncio.sleep(wait_time)
    return canvas[x, y]


async def assign_free_task(user_id: int) -> Task:
    """Assign a free task to `user_id`, raise 409 on fail"""
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


def unassign_task(user_id: int) -> None:
    """Unassign given `task` from `user_id` and mark it free to be claimed"""
    global tasks
    global free_tasks

    task = tasks[user_id]
    del tasks[user_id]
    free_tasks.append(task)


async def reload_loop() -> None:
    """
    Keep continually querying the database to update the list of projects, these updates aren't
    that common, but they happen when a new project is added/removed/edited
    """
    global projects

    while True:
        async with constants.DB_POOL.acquire() as db_conn:
            db_projects = await db_conn.fetch("SELECT * FROM projects")

        local_projects = []
        for db_project in db_projects:
            project_model = ProjectDetails(
                name=db_project["project_name"],
                x=db_project["position_x"],
                y=db_project["position_y"],
                priority=db_project["project_priority"],
                image=db_project["base64_image"]
            )
            local_projects.append(project_model)

        projects = local_projects
        await update_tasks()
        await asyncio.sleep(constants.task_refresh_time)


async def update_tasks() -> None:
    global free_tasks
    global update_time
    global canvas

    canvas = await constants.CLIENT.get_canvas()

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

    update_time = time.time()
