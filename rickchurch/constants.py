# type: ignore - config function gives str|bool|Unknown, we specify it with type-hint
import asyncpg
from decouple import config


DISCORD_BASE_URL = "https://discord.com/api"

log_level: str = config("LOG_LEVEL", default="INFO")

base_url: str = config("BASE_URL")  # URL to host church of rick

# Get these from https://discord.com/developers/applications, OAuth2 section
client_id: str = config("CLIENT_ID")
client_secret: str = config("CLIENT_SECRET")
# Get this by adding {base_url}/oauth_callback as URI in the application's OAuth2 section
oauth_redirect_url: str = config("OAUTH_REDIRECT_URL")

discord_guild_id: str = config("DISCORD_GUILD_ID")
discord_bot_token: str = config("DISCORD_BOT_TOKEN")

jwt_secret: str = config("JWT_SECRET")
pixels_api_token: str = config("PIXELS_API_TOKEN")

# PostgreSQL Database
database_url: str = config("DATABASE_URL")
min_pool_size: int = config("MIN_POOL_SIZE", cast=int, default=2)
max_pool_size: int = config("MAX_POOL_SIZE", cast=int, default=5)
# Awaited in application startup
DB_POOL = asyncpg.create_pool(database_url, min_size=min_pool_size, max_size=max_pool_size)

with open("rickchurch/resources/mods.txt") as f:
    mods = [int(entry) for entry in f.read().split()]
