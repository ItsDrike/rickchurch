import logging
from typing import Any, Dict, Optional

import pydispix
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from rickchurch import constants

logger = logging.getLogger(__name__)
app = FastAPI()
client: Optional[pydispix.Client] = None
canvas: Optional[pydispix.Canvas] = None


def custom_openapi() -> Dict[str, Any]:
    """Creates a custom OpenAPI schema."""
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="Pixels API",
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
    """Create asyncpg connection pool on startup."""
    # We have to make a global client and canvas objects as there is no way for
    # us to send the objects to the following requests from this function.
    global client
    global canvas
    client = pydispix.Client(constants.pixels_api_token)
    canvas = await client.get_canvas()

    # Initialize DB connection
    await constants.DB_POOL


@app.on_event("shutdown")
async def shutdown() -> None:
    """Close down the app."""
    await constants.DB_POOL.close()
