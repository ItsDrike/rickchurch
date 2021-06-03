import logging
from typing import Any, Callable, Dict, List, Optional

import fastapi
import pydispix
from fastapi.openapi.utils import get_openapi
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from rickchurch import constants
from rickchurch.auth import add_user, authorized
from rickchurch.log import setup_logging
from rickchurch.models import Message, Project, User
from rickchurch.utils import fetch_projects, get_oauth_user

logger = logging.getLogger("rickchurch")
app = fastapi.FastAPI()
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
    openapi_schema["components"]["securitySchemes"] = {
        "Bearer": {
            "type": "http",
            "scheme": "Bearer"
        }
    }
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
    # We have to make a global client object as there is no way for us to
    # send the objects to the following requests from this function.
    global client
    client = pydispix.Client(constants.pixels_api_token)

    setup_logging(constants.log_level)

    # Initialize DB connection
    await constants.DB_POOL


@app.on_event("shutdown")
async def shutdown() -> None:
    """Close down the app."""
    await constants.DB_POOL.close()


@app.middleware("http")
async def setup_data(request: fastapi.Request, callnext: Callable) -> fastapi.Response:
    """Get a connection from the pool and a canvas reference for this request."""
    async with constants.DB_POOL.acquire() as db_connection:
        request.state.db_conn = db_connection
        request.state.client = client
        request.state.auth = await authorized(request.headers.get("Authorization"), db_connection)
        response = await callnext(request)
    request.state.db_conn = None
    request.state.client = None
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
    code = request.query_params["code"]
    try:
        user = await get_oauth_user(code)
        token = await add_user(user, request.state.db_conn)
    except PermissionError:
        # `add_user` can return `PermissionError` if the user already has a token, which is banned.
        raise fastapi.HTTPException(401, "You are banned")

    # Redirect so that a user doesn't refresh the page and spam discord
    redirect = RedirectResponse("/show_token", status_code=303)
    redirect.set_cookie(
        key='token',
        value=token,
        httponly=True,
        max_age=10,
        path='/show_token',
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

@app.get("/", include_in_schema=False, tags=["Member endpoint"])
async def index(request: fastapi.Request) -> fastapi.Response:
    return templates.TemplateResponse("index.html", {"request": request})


# endregion
# region: Member API Endpoints

@app.get("/get_projects", tags=["Member endpoint"], response_model=List[Project])
async def get_projects(request: fastapi.Request) -> List[Project]:
    """Obtain all active project data."""
    request.state.auth.raise_if_failed()
    return await fetch_projects(request.state.db_conn)


# endregion
# region: Moderation API endpoints

@app.get("/mod", tags=["Moderation Endpoint"], response_model=Message)
async def mod_check(request: fastapi.Request) -> Message:
    """Check if the authenticated user is a mod."""
    request.state.auth.raise_unless_mod()
    return Message(message="You are a moderator!")


@app.post("/set_mod", tags=["Moderation endpoint"], response_model=Message)
async def set_mod(request: fastapi.Request, user: User) -> Message:
    request.state.auth.raise_unless_mod()

    db_conn = request.state.db_conn
    async with db_conn.transaction():
        user_state = await db_conn.fetchrow("SELECT is_mod FROM users WHERE user_id = $1;", user.user_id)

        if user_state is None:
            return Message(message=f"User with user_id {user.user_id} does not exist.")
        elif user_state['is_mod']:
            return Message(message=f"User with user_id {user.user_id} is already a mod.")

        await db_conn.execute("UPDATE users SET is_mod = true WHERE user_id = $1;", user.user_id)
    return Message(message=f"Successfully set user with user_id {user.user_id} to mod")

# endregion
