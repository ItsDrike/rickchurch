import logging
from typing import Optional

import pydispix
from fastapi import FastAPI

from rickchurch import constants

logger = logging.getLogger(__name__)
app = FastAPI()
client: Optional[pydispix.Client] = None
canvas: Optional[pydispix.Canvas] = None


@app.on_event("startup")
async def startup() -> None:
    # We have to make a global client and canvas objects as there is no way for
    # us to send the objects to the following requests from this function.
    global client
    global canvas
    client = pydispix.Client(constants.pixels_api_token)
    canvas = await client.get_canvas()
