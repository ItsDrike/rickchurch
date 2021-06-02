# type: ignore - config function gives str|bool|Unknown, we specify it with type-hint
import asyncpg
from decouple import config

jwt_secret: str = config("JWT_SECRET")
pixels_api_token: str = config("PIXELS_API_TOKEN")
log_level: str = config("LOG_LEVEL", default="INFO")

base_url: str = config("BASE_URL")  # URL to host church of rick
discord_token_url: str = config("TOKEN_URL", default="https://discord.com/api/oauth2/token")
discord_user_url: str = config("USER_URL", default="https://discord.com/api/users/@me")

# Get these from https://discord.com/developers/applications, OAuth2 section
client_id: str = config("CLIENT_ID")
client_secret: str = config("CLIENT_ID")

# PostgreSQL Database
database_url: str = config("DATABASE_URL")
min_pool_size: int = config("MIN_POOL_SIZE", cast=int, default=2)
max_pool_size: int = config("MAX_POOL_SIZE", cast=int, default=5)
# Awaited in application startup
DB_POOL = asyncpg.create_pool(
    database_url,
    min_size=min_pool_size,
    max_size=max_pool_size
)

with open("rickchurch/resources/mods.txt") as f:
    mods = [int(entry) for entry in f.read().split()]
