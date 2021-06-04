# Church of Rick central API

[![made-with-python](https://img.shields.io/badge/Made%20with-Python%203.8+-ffe900.svg?longCache=true&style=flat-square&colorB=00a1ff&logo=python&logoColor=88889e)](https://www.python.org/)
[![AGPL](https://img.shields.io/badge/Licensed%20under-AGPL-red.svg?style=flat-square)](./LICENSE)
[![Validation](https://github.com/ItsDrike/rickchurch/actions/workflows/validation.yaml/badge.svg)](https://github.com/ItsDrike/rickchurch/actions/workflows/validation.yaml?style=flat-square)

A central API server to distribute pixel placement tasks to the members of the
[Church of Rick™](https://pixel-tasks.scoder12.repl.co)

## Setting it up

To run your own development testing version of the API, follow these steps:

### First, setup the environmental variables

1. Make a `.env` file in the project's root directory to store your environmental variables
2. Make an application in [discord developers portal](https://discord.com/developers/applications)
3. Go to `OAuth2` section, and set your environmental variables for `CLIENT_ID` and `CLIENT_SECRET` accordingly to the Client Information in this section
4. Decide which URL should be used to access the API (if you're just testing, use `http://localhost:8000`), and set it as `BASE_URL` env variable
5. Set URI (redirect URL) in the discord application to: `[BASE_URL]/oauth_callback`, so in our case: `http://localhost:8000/oauth_callback`
6. Generate the OAuth2 URL with the `identify` scope. If you plan to use autojoin, you
   also need the `guilds.join` scope. Set `OAUTH_REDIRECT_URL` to the generated URL.
7. Set `JWT_SECRET` variable to some secret, this will be used to encode the JWT tokens, make sure it's secure enough
8. Set `PIXELS_API_TOKEN` variable, this will be the token you got from the [official python-discord's webpage](https://pixels.pythondiscord.com/info/)
9. You can also set `LOG_LEVEL` variable, to control the logging level that should be used, this defaults to `INFO`, set it to `DEBUG` if you need to
10. To enable automatic joining of users into your discord guild, create a bot user in
    the same discord application you used for OAuth and invite it to the guild you want
    to use. Next, set `ENABLE_DISCORD_AUTOJOIN` to `1`, `DISCORD_GUILD_ID` to the ID of
    the guild you want to use, and `DISCORD_BOT_TOKEN` to the token of your discord bot.
11. Refer to `rickchurch/constants.py` for more information on how to configure the
    application.

### Setup the running environment

You can use the `docker-compose` which is more than sufficient for testing:
_Note: this guide is meant for linux, if you're on windows, search how to run docker-compose there_

1. Install docker, specifically `docker-compose`. (I won't detail this, for Arch Linux it's `pacman -S docker-compose`)
2. Go to the into the root of the repository. (`cd /path/to/rickchurch`)
3. Simply run `docker-compose up` (you might need `sudo`)
4. The API is now running at `localhost:8000`, and if you need to access the postgresql database, it's at `localhost:5000`

If you need to run production server on bare-metal, you will have to setup PostgreSQL database on your own. ([Guide for Arch Linux](https://wiki.archlinux.org/title/PostgreSQL))
After you're done, set `DATABASE_URL` env variable pointing to it (see example in [docker-compose.yml](docker-compose.yml)).
You should be able to run the API now.
