import logging
from typing import Any, Callable, Dict, List, Optional

import fastapi
import pydispix
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from rickchurch import constants
from rickchurch.auth import authorized
from rickchurch.log import setup_logging
from rickchurch.models import Project
from rickchurch.utils import fetch_projects

logger = logging.getLogger("rickchurch")
app = fastapi.FastAPI()
client: Optional[pydispix.Client] = None

app.mount("/static", StaticFiles(directory="rickchurch/static"), name="static")
templates = Jinja2Templates(directory="pixels/templates")


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
    async with constants.DB_POOL.acquire() as connection:
        request.state.db_conn = connection
        request.state.client = client
        request.state.auth = await authorized(connection, request.headers.get("Authorization"))
        response = await callnext(request)
    request.state.db_conn = None
    request.state.client = None
    return response


# region: Member Endpoints

@app.get("/get_projects", tags=["Member endpoint"], response_model=List[Project])
async def get_projects(request: fastapi.Request) -> List[Project]:
    request.state.auth.raise_if_failed()
    return await fetch_projects(request.state.db_conn)

# endregion
