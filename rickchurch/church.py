import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

import fastapi
import httpx
import pydispix
from fastapi.openapi.utils import get_openapi
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from rickchurch import constants, tasks
from rickchurch.auth import add_user, authorized
from rickchurch.log import setup_logging
from rickchurch.models import Message, Project, ProjectDetails, Task, User
from rickchurch.utils import fetch_projects, get_oauth_user

logger = logging.getLogger("rickchurch")
app = fastapi.FastAPI(docs_url=None, redoc_url=None)
client: Optional[pydispix.Client] = None

app.mount("/static", StaticFiles(directory="rickchurch/static"), name="static")
templates = Jinja2Templates(directory="rickchurch/templates")


def custom_openapi() -> Dict[str, Any]:
    """Creates a custom OpenAPI schema."""
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="Rick Church API",
        description=None,
        version="1.0.0",
        routes=app.routes,
    )
    # fmt: off
    openapi_schema["components"]["securitySchemes"] = {
        "Bearer": {
            "type": "http",
            "scheme": "Bearer"
        }
    }
    # fmt: on
    for route in app.routes:
        # Use getattr as not all routes have this attr
        if not getattr(route, "include_in_schema", False):
            continue
        # Pyright/Pylance can't detect these attributes, ignore typing here
        route_path = route.path  # type: ignore
        methods = route.methods  # type: ignore

        # For each method the path provides insert the Bearer security type
        for method in methods:
            openapi_schema["paths"][route_path][method.lower()]["security"] = [{"Bearer": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.on_event("startup")
async def startup() -> None:
    """Create asyncpg connection pool on startup and setup logging."""
    app.state.httpx_client = httpx.AsyncClient()
    setup_logging(constants.log_level)

    # Initialize DB connection
    await constants.DB_POOL

    # Start refreshing tasks
    asyncio.create_task(tasks.reload_loop())


@app.on_event("shutdown")
async def shutdown() -> None:
    """Close down the app."""
    await app.state.httpx_client.aclose()
    await constants.DB_POOL.close()


@app.middleware("http")
async def setup_data(request: fastapi.Request, callnext: Callable) -> fastapi.Response:
    """Get a connection from the pool and a canvas reference for this request."""
    async with constants.DB_POOL.acquire() as db_connection:
        request.state.db_conn = db_connection
        request.state.auth = await authorized(request.headers.get("Authorization"), db_connection)
        response = await callnext(request)
    request.state.db_conn = None
    request.state.db_client = None
    return response


# region: Discord OAuth2


@app.get("/authorize", tags=["Authorization Endpoints"], include_in_schema=False)
async def authorize() -> fastapi.Response:
    """
    Redirect the user to discord authorization, the flow continues in /oauth_callback.
    Unlike other endpoints, you should open this one in the browser, since it redirects to a discord website.
    """
    return RedirectResponse(url=constants.oauth_redirect_url)


@app.get("/oauth_callback", include_in_schema=False)
async def auth_callback(request: fastapi.Request) -> fastapi.Response:
    """This endpoint is only used as a redirect target from discord OAuth2."""
    httpx_client: httpx.AsyncClient = request.app.state.httpx_client
    code = request.query_params["code"]
    try:
        user, access_token = await get_oauth_user(httpx_client, code)
        token = await add_user(user, request.state.db_conn)
    except PermissionError:
        # `add_user` can return `PermissionError` if the user already has a token, which is banned.
        raise fastapi.HTTPException(401, "You are banned")

    if constants.enable_auto_join:
        # TODO: Make this a fastapi background task?
        res = await httpx_client.put(
            f"{constants.DISCORD_BASE_URL}/guilds/{constants.discord_guild_id}/members/{user['id']}",
            json={"access_token": access_token},
            headers={"Authorization": f"Bot {constants.discord_bot_token}"},
        )
        # 200: Success: Misc success
        # 201: Created: user joined the server
        # 204: No content: user already in the server
        if res.status_code not in (200, 201, 204):
            try:
                # repr makes sure that no weird characters get printed and also allows
                #  user to determine between response text of 'N/A' and real N/A
                text = repr(res.text)
            except Exception:
                text = "N/A"
            logger.error(f"Joining server for user failed: Code {res.status_code} text {text}")

    # Redirect so that a user doesn't refresh the page and spam discord
    redirect = RedirectResponse("/show_token", status_code=303)
    redirect.set_cookie(
        key="token",
        value=token,
        httponly=True,
        max_age=10,
        path="/show_token",
    )
    return redirect


@app.get("/show_token", include_in_schema=False)
async def show_token(request: fastapi.Request, token: str = fastapi.Cookie(None)) -> fastapi.Response:  # noqa: B008
    """Take a token from URL and show it."""
    template_name = "cookie_disabled.html"
    context: dict[str, Any] = {"request": request}

    if token:
        context["token"] = token
        template_name = "api_token.html"

    return templates.TemplateResponse(template_name, context)


# endregion
# region: General Endpoints


@app.get("/", include_in_schema=False, tags=["General endpoint"])
async def index(request: fastapi.Request) -> fastapi.Response:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/docs", include_in_schema=False, tags=["General endpoint"])
async def docs(request: fastapi.Request) -> fastapi.Response:
    return templates.TemplateResponse("docs.html", {"request": request})


@app.get("/info", include_in_schema=False, tags=["General endpoint"])
async def roll(request: fastapi.Request) -> fastapi.Response:
    """Include a rickroll for good measures"""
    return RedirectResponse("https://youtu.be/dQw4w9WgXcQ", status_code=303)


# endregion
# region: Member API Endpoints


@app.get("/projects", tags=["Member endpoint"], response_model=List[ProjectDetails])
async def get_projects(request: fastapi.Request) -> List[ProjectDetails]:
    """Obtain all active project data."""
    request.state.auth.raise_if_failed()
    return await fetch_projects(request.state.db_conn)


@app.get("/task", tags=["Member endpoint"], response_model=Task)
async def get_task(request: fastapi.Request) -> Task:
    request.state.auth.raise_if_failed()
    user_id = request.state.auth.user_id
    return await tasks.assign_free_task(user_id)


@app.post("/task", tags=["Member endpoint"], response_model=Message)
async def post_task(request: fastapi.Request, task: Task) -> Message:
    request.state.auth.raise_if_failed()
    user_id = request.state.auth.user_id
    await tasks.submit_task(task, user_id)
    return Message(message="Task submitted successfully.")


# endregion
# region: Moderation API endpoints


@app.get("/mods/check", tags=["Moderation Endpoint"], response_model=Message)
async def mod_check(request: fastapi.Request) -> Message:
    """Check if the authenticated user is a mod."""
    request.state.auth.raise_unless_mod()
    return Message(message="You are a moderator!")


@app.post("/mods/promote", tags=["Moderation endpoint"], response_model=Message)
async def promote_mod(request: fastapi.Request, user: User) -> Message:
    """Make another user a moderator"""
    request.state.auth.raise_unless_mod()

    db_conn = request.state.db_conn
    async with db_conn.transaction():
        user_state = await db_conn.fetchrow("SELECT is_mod FROM users WHERE user_id = $1;", user.user_id)

        if user_state is None:
            raise fastapi.HTTPException(status_code=404, detail=f"User with user_id {user.user_id} does not exist.")
        elif user_state["is_mod"]:
            raise fastapi.HTTPException(status_code=409, detail=f"User with user_id {user.user_id} is already a mod")

        await db_conn.execute("UPDATE users SET is_mod = true WHERE user_id = $1;", user.user_id)
    return Message(message=f"Successfully promoted user with user_id {user.user_id} to mod")


@app.post("/mods/demote", tags=["Moderation endpoint"], response_model=Message)
async def demote_mod(request: fastapi.Request, user: User) -> Message:
    """Make another user a moderator"""
    request.state.auth.raise_unless_mod()

    db_conn = request.state.db_conn
    async with db_conn.transaction():
        user_state = await db_conn.fetchrow("SELECT is_mod FROM users WHERE user_id = $1;", user.user_id)

        if user_state is None:
            raise fastapi.HTTPException(status_code=404, detail=f"User with user_id {user.user_id} does not exist.")
        elif user_state["is_mod"] is False:
            raise fastapi.HTTPException(status_code=409, detail=f"User with user_id {user.user_id} isn't a mod.")

        await db_conn.execute("UPDATE users SET is_mod = false WHERE user_id = $1;", user.user_id)
    return Message(message=f"Successfully demoted user with user_id {user.user_id} to regular user")


@app.post("/mods/ban", tags=["Moderation endpoint"], response_model=Message)
async def ban_user(request: fastapi.Request, user: User) -> Message:
    """Ban users from using the API."""
    request.state.auth.raise_unless_mod()

    db_conn = request.state.db_conn
    db_user = await db_conn.fetch("SELECT * FROM users WHERE user_id=$1", user.user_id)

    if not db_user:
        raise fastapi.HTTPException(status_code=404, detail=f"User with user_id {user.user_id} does not exist.")

    await db_conn.execute("UPDATE users SET is_banned=TRUE WHERE user_id=$1", user.user_id)
    return Message(message=f"Successfully banned user_id {user.user_id}")


@app.post("/mods/project", tags=["Moderation endpoint"], response_model=Message)
async def add_project(request: fastapi.Request, project: ProjectDetails) -> Message:
    """Add a new project"""
    request.state.auth.raise_unless_mod()

    db_conn = request.state.db_conn
    db_project = await db_conn.fetchrow("SELECT * FROM projects WHERE project_name=$1", project.name)

    if db_project is not None:
        raise fastapi.HTTPException(status_code=409, detail=f"Database project {project.name} already exists.")

    # fmt: off
    await db_conn.execute(
        """INSERT INTO projects (project_name, position_x, position_y, project_priority, base64_image)
        VALUES ($1, $2, $3, $4, $5)""",
        project.name, project.x, project.y, project.priority, project.image
    )
    # fmt: on
    return Message(message=f"Project {project.name} was added successfully.")


@app.delete("/mods/project", tags=["Moderation endpoint"], response_model=Message)
async def remove_project(request: fastapi.Request, project: Project) -> Message:
    """Add a new project"""
    request.state.auth.raise_unless_mod()

    db_conn = request.state.db_conn
    db_project = await db_conn.fetchrow("SELECT * FROM projects WHERE project_name=$1", project.name)

    if db_project is None:
        raise fastapi.HTTPException(status_code=404, detail=f"Database project {project.name} doesn't exist.")

    await db_conn.execute("DELETE FROM projects WHERE project_name=$1", project.name)
    return Message(message=f"Project {project.name} was removed successfully.")


@app.put("/mods/project", tags=["Moderation endpoint"], response_model=Message)
async def put_project(request: fastapi.Request, project: ProjectDetails) -> Message:
    """Update an existing project"""
    request.state.auth.raise_unless_mod()

    db_conn = request.state.db_conn
    db_project = await db_conn.fetchrow("SELECT * FROM projects WHERE project_name=$1", project.name)

    if db_project is None:
        raise fastapi.HTTPException(status_code=404, detail=f"Database project {project.name} doesn't exist.")

    # fmt: off
    await db_conn.execute(
        """UPDATE projects SET project_name=$1, position_x=$2, position_y=$3, project_priority=$4, base64_image=$5
        WHERE project_name=$1""",
        project.name, project.x, project.y, project.priority, project.image
    )
    # fmt: on
    return Message(message=f"Project {project.name} was updated successfully.")


# endregion
