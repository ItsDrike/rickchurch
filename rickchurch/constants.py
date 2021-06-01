# type: ignore - config function gives str|bool|Unknown, we specify it with type-hint
from decouple import config


pixels_api_token: str = config("PIXELS_API_TOKEN")
log_level: str = config("LOG_LEVEL", default="INFO")
