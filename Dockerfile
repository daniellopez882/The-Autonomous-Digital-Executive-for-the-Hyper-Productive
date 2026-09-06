# Two stages so the build toolchain does not ship in the runtime image.
FROM python:3.12-slim AS build

WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt


FROM python:3.12-slim AS runtime

# Not root. The OAuth token this process writes is a credential; a container
# that runs as uid 0 writes it into a root-owned volume that nothing else can
# rotate.
RUN useradd --create-home --uid 10001 nexus

WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --chown=nexus:nexus src/ ./src/

# credentials/ holds the OAuth token. It must be a mounted volume: baking it
# into an image puts a refresh token into every layer that image is pushed to.
RUN mkdir -p /app/credentials && chown nexus:nexus /app/credentials
VOLUME ["/app/credentials"]

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER nexus

# The preflight is the health check: it exits non-zero when a required
# dependency is missing, which is the whole point of replacing "Systems at 100%".
HEALTHCHECK --interval=60s --timeout=20s --start-period=10s --retries=2 \
    CMD ["python", "-m", "src.main", "--check"]

ENTRYPOINT ["python", "-m", "src.main"]
CMD ["--check"]
