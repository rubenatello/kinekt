ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim AS builder

COPY --from=ghcr.io/astral-sh/uv@sha256:93b61e21202b1dab861092748e46bbd6e0e41dd84f59b9174efd2353186e1b47 \
    /uv /uvx /bin/

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=60 \
    PIP_RETRIES=10 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

COPY pyproject.toml uv.lock /build/

RUN --mount=type=cache,target=/root/.cache/pip \
    uv export --locked --extra dev --extra mcp --no-emit-project --no-hashes \
        --output-file /tmp/requirements.txt \
    && python -m pip wheel --wheel-dir /wheels --requirement /tmp/requirements.txt

COPY README.md /build/
COPY src /build/src

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip wheel --no-deps --wheel-dir /wheels .


FROM python:${PYTHON_VERSION}-slim AS runtime

ARG KINEKT_GID=10001
ARG KINEKT_UID=10001

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=60 \
    PIP_RETRIES=10 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --no-install-recommends --yes ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${KINEKT_GID}" kinekt \
    && useradd --create-home --gid "${KINEKT_GID}" --uid "${KINEKT_UID}" kinekt

COPY --from=builder /wheels /wheels

RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels --upgrade pip setuptools \
    && python -m pip install --no-cache-dir --no-index --find-links=/wheels "kinekt[mcp]" \
    && rm -rf /wheels \
    && mkdir -p /workspace \
    && chown kinekt:kinekt /workspace

USER kinekt
WORKDIR /workspace

ENTRYPOINT ["kinekt"]
CMD ["--help"]


FROM runtime AS test

USER root
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels "kinekt[dev]"
COPY tests /tests
COPY scripts /tests/scripts
USER kinekt
WORKDIR /tests
ENTRYPOINT ["python", "-m", "pytest"]
CMD ["-q", "-p", "no:cacheprovider"]


FROM runtime AS final
