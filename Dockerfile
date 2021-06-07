FROM tiangolo/uvicorn-gunicorn-fastapi:python3.8

# Set pip to have no saved cache
ENV PIP_NO_CACHE_DIR=false \
    MODULE_NAME="rickchurch" \
    MAX_WORKERS=1

# Install poetry
RUN curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | POETRY_HOME=/opt/poetry python && \
    cd /usr/local/bin && \
    ln -s /opt/poetry/bin/poetry && \
    poetry config virtualenvs.create false

# Copy using poetry.lock* in case it doesn't exist yet
COPY ./pyproject.toml ./poetry.lock* /app/

# Install project dependencies
RUN poetry install --no-dev --no-root

# Copy the source code in last to optimize rebuilding the image
COPY . /app
