import random
from functools import partial

import fastapi

from rickchurch import constants
from rickchurch.models import Task
from rickchurch.utils import postpone

# Use global variables to keep track of current task list,
# this isn't ideal, but it's the easiest solution we can use.
tasks = {}
free_tasks = []


def submit_task(task: Task, user_id: int):
    """Try to submit a `task` from `user_id`"""
    global tasks

    # This performs a linear search across the tasks, with our userbase, this shouldn't be an issue
    # it is here to provide more detailed info to the client, since the task doesn't actually exists
    # at all, and not just respond with reassigned.
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
