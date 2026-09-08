# Container images

Container tasks are selected with the optional `containers` tag. They generate a multi-stage Dockerfile from the project metadata and container settings, build the application wheel, and install it in a non-root runtime image. A consuming project does not need to maintain its own application Dockerfile.

```toml
[tool.poe]
include_script = "common_python_tasks:tasks(include_tags=['common', 'containers'])"
```

## How the generated Dockerfile works

`build-image` renders a temporary Dockerfile and uses the project root as its build context. If the project does not provide `.dockerignore`, the task temporarily supplies a conservative default that includes `pyproject.toml`, `uv.lock`, `README.md`, `LICENSE`, and the `src/` tree.

The generated Dockerfile contains the following stages.

| Stage | Purpose |
| - | - |
| `builder` | Uses the host Python version, installs the installed version of uv, exports the optional `debug` dependency group, and builds the project wheel. |
| `runtime` | Uses the configured Python image variant, installs optional APT packages and dependency-image artifacts, creates the non-root `py` user, installs the wheel, creates the `/pkg` package link and entrypoint, and applies container extensions. |
| `debug` | Extends `runtime` with the project source and the `debug` dependency group. This stage exists only when `[dependency-groups].debug` is non-empty. |
| `final` | Extends `runtime` so tools that build the rendered Dockerfile without selecting a target still produce the normal runtime image. |

The `build-image` task explicitly builds `runtime`, or `debug` when `--debug` is used. A debug build fails early when the project has no non-empty `debug` dependency group.

The task supplies build arguments derived from the current environment and project metadata, including `PYTHON_VERSION`, `UV_VERSION`, `PACKAGE_VERSION`, `PACKAGE_NAME`, `AUTHORS`, `GIT_COMMIT`, `PYTHON_VARIANT`, and `WORKDIR_PATH`. It also creates short and fully qualified image tags for the package version and Git commit. A dirty working tree adds `-dirty` to the commit tag.

### Generic template reference

The complete templates below are copied from the package source during documentation generation. The preceding stage table explains how their major sections fit together. Run `poe update-docs-references` after changing either template, or `poe check-docs-references` to verify that the checked-in copies are current.

<!-- generated-dockerfile-reference -->

### Application image template

Source: [`Dockerfile.j2`](https://github.com/ci-sourcerer/common-python-tasks/blob/main/src/common_python_tasks/data/generic/Dockerfile.j2)

```dockerfile
# syntax=docker/dockerfile:1

# It is wise to use the Python version you are developing with and not blindly choose
# the latest. The `build-image` task passes the version properly here
ARG PYTHON_VERSION=3
# Variant for the runtime image, e.g. slim, alpine, etc.
# See https://hub.docker.com/_/python for available variants. Leave empty for no variant.
ARG PYTHON_VARIANT=slim

FROM python:${PYTHON_VERSION} AS builder

ARG PACKAGE_VERSION
ARG UV_VERSION

{% if CONTAINER_ENV_VARS %}
# Make configured variables available to package build commands.
{% for env_var in CONTAINER_ENV_VARS -%}
ENV {{ env_var }}
{% endfor %}
{%- endif %}

# Bypass VCS-based version detection: use the host-computed version directly.
# This avoids requiring a .git directory in the build context and prevents
# false dirty-version detection from a partial working tree.
ENV UV_DYNAMIC_VERSIONING_BYPASS=${PACKAGE_VERSION}

# Install uv for package build and dependency export steps
RUN --mount=type=cache,target=/root/.cache/pip,id=pip-cache{{ CACHE_ID_SUFFIX }} \
    sh -c 'if [ -n "${UV_VERSION:-}" ]; then \
        pip install --root-user-action=ignore "uv==$UV_VERSION"; \
    else \
        pip install --root-user-action=ignore uv; \
    fi'

# Build package
WORKDIR /tmp/build
COPY . /tmp/build/

{% if HAS_DEBUG_DEPS %}
# Export debug requirements when the project defines a debug dependency group
RUN --mount=type=cache,target=/root/.cache/uv,id=uv-cache{{ CACHE_ID_SUFFIX }}{% for mount in UV_INDEX_SECRET_MOUNTS %} \
    --mount={{ mount }}{% endfor %} \
    uv export --group debug --no-hashes --format requirements-txt --output-file requirements-debug.txt
{% endif %}

# Build the wheel, caching the uv cache directory to speed up subsequent builds.
# If running this in a CI system, you must be using a persistent builder to take
# advantage of the cache mount, and you should configure your CI to persist the
# cache directory between builds
RUN --mount=type=cache,target=/root/.cache/uv,id=uv-cache{{ CACHE_ID_SUFFIX }}{% for mount in UV_INDEX_SECRET_MOUNTS %} \
    --mount={{ mount }}{% endfor %} \
    uv build --wheel

FROM python:${PYTHON_VERSION}${PYTHON_VARIANT:+-${PYTHON_VARIANT}} AS runtime
ARG PYTHON_VERSION
ARG PYTHON_VARIANT
ARG WORKDIR_PATH=/workspace

LABEL org.opencontainers.image.base.name="python:${PYTHON_VERSION}${PYTHON_VARIANT:+-${PYTHON_VARIANT}}" \
      org.opencontainers.image.python.variant="${PYTHON_VARIANT}"

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

ARG NONROOT_USERNAME=py
ARG NONROOT_UID=1000
ARG NONROOT_GID=1000

{% if CONTAINER_ENV_VARS %}
# Persist the same variables for runtime build commands and running containers.
{% for env_var in CONTAINER_ENV_VARS -%}
ENV {{ env_var }}
{% endfor %}
{%- endif %}

ENV DEBIAN_FRONTEND=noninteractive
{% if CONTAINER_APT_PACKAGES %}
# Install optional runtime apt packages selected by Python-side template rendering
RUN --mount=type=cache,target=/var/cache/apt,id=apt-cache{{ CACHE_ID_SUFFIX }} \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked,id=apt-lists{{ CACHE_ID_SUFFIX }} \
    apt-get update && apt-get install -y --no-install-recommends {{ CONTAINER_APT_PACKAGES }}
{% endif %}
{% if CONTAINER_DEPS_IMAGE %}

# Pull external dependencies from the pre-built deps image
ARG CONTAINER_DEPS_IMAGE
COPY --from={{ CONTAINER_DEPS_IMAGE }} /tmp/deps /tmp/deps
{% endif %}
{% if CONTAINER_DEPS_MOVE_SCRIPT %}
RUN set -eux; \
    cat >/tmp/container-deps-move-script <<'SCRIPT' && \
    chmod +x /tmp/container-deps-move-script && \
    /tmp/container-deps-move-script
{{ CONTAINER_DEPS_MOVE_SCRIPT }}
SCRIPT
{% endif %}

# Create a named non-root user with a writable home directory
# Written to cover all Python image variants
RUN set -eux; \
    if adduser --help 2>&1 | grep -q -- '--disabled-password'; then \
        addgroup --gid "${NONROOT_GID}" "${NONROOT_USERNAME}"; \
        adduser --uid "${NONROOT_UID}" --gid "${NONROOT_GID}" --home "${WORKDIR_PATH}" --shell /bin/sh --disabled-password --gecos '' "${NONROOT_USERNAME}"; \
    else \
        addgroup -g "${NONROOT_GID}" "${NONROOT_USERNAME}" && \
        adduser -D -u "${NONROOT_UID}" -G "${NONROOT_USERNAME}" -h "${WORKDIR_PATH}" -s /bin/sh "${NONROOT_USERNAME}"; \
    fi; \
    mkdir -p "${WORKDIR_PATH}"; \
    chown -R "${NONROOT_USERNAME}":"${NONROOT_USERNAME}" "${WORKDIR_PATH}"

WORKDIR ${WORKDIR_PATH}

# Grab package from builder image
COPY --from=builder /tmp/build/dist/*.whl /tmp/

# Install package
RUN --mount=type=cache,target=/root/.cache/pip,id=pip-cache{{ CACHE_ID_SUFFIX }} pip install --root-user-action=ignore /tmp/*.whl
# Create symlinks for the package
ARG PACKAGE_NAME
ENV PACKAGE_NAME=${PACKAGE_NAME}
RUN ln -s "$(python -c "import os; from importlib import resources; print(resources.files(os.environ['PACKAGE_NAME']))")" "/_$PACKAGE_NAME" \
    && ln -s "/_$PACKAGE_NAME" "/pkg" \
    && rm -rf "/_$PACKAGE_NAME/__pycache__"

ENTRYPOINT ["/pkg/entrypoint.sh"]

ARG AUTHORS
ARG GIT_COMMIT
LABEL org.opencontainers.image.authors=${AUTHORS}
LABEL git.commit=${GIT_COMMIT}

# Set custom entrypoint if provided
# This entrypoint is deliberately not configurable via environment variables in order to
# ensure that the container always uses the entrypoint selected at build time. If the
# current package does not provide a console script, the entrypoint will default to `python`
RUN echo "#!/bin/sh

{{ ENTRYPOINT_COMMAND|default('python') }} \"\$@\"" >/pkg/entrypoint.sh \
    && chmod +x /pkg/entrypoint.sh

USER py

{% if EXTENSION_CONTENT %}
{{ EXTENSION_CONTENT }}
{% endif %}

{% if HAS_DEBUG_DEPS %}
# Optional debug stage: only installs debug deps if they were exported. This stage will not
# be built by default (the final stage below is the runtime image), and it will safely do
# nothing if there are no debug requirements
FROM runtime AS debug

USER root

COPY --from=builder /tmp/build /tmp/build

RUN --mount=type=cache,target=/root/.cache/pip,id=pip-cache{{ CACHE_ID_SUFFIX }} pip install --root-user-action=ignore -r /tmp/build/requirements-debug.txt

USER py
{% endif %}

# Final (default) image: explicitly use runtime as the final target so debug is not used unless requested
FROM runtime AS final

USER py
```

### Dependency image template

Source: [`Dockerfile.deps.j2`](https://github.com/ci-sourcerer/common-python-tasks/blob/main/src/common_python_tasks/data/generic/Dockerfile.deps.j2)

```dockerfile
# syntax=docker/dockerfile:1

# Dependency collector image: installs external dependencies into /tmp/deps
# so the main application Dockerfile can COPY --from this image.
ARG PYTHON_VERSION=3
ARG PYTHON_VARIANT=slim

FROM python:${PYTHON_VERSION}${PYTHON_VARIANT:+-${PYTHON_VARIANT}} AS deps
ARG PYTHON_VERSION
ARG PYTHON_VARIANT

LABEL org.opencontainers.image.base.name="python:${PYTHON_VERSION}${PYTHON_VARIANT:+-${PYTHON_VARIANT}}" \
      org.opencontainers.image.python.variant="${PYTHON_VARIANT}"

ARG CACHE_ID_SUFFIX
RUN printf '%s' "$CACHE_ID_SUFFIX" >/tmp/.cache_id_suffix

ENV DEBIAN_FRONTEND=noninteractive

RUN mkdir -p /tmp/deps

{{ DEPS_CONTENT }}
```

<!-- end-generated-dockerfile-reference -->

### Runtime defaults

The runtime image uses `python:<host-version>-slim` by default. Set `CONTAINER_PYTHON_VARIANT` to another official Python image variant, or to an empty string to use `python:<host-version>` without a suffix. `CONTAINER_APT_PACKAGES` is rendered as a space-delimited package list in an `apt-get install` command, so it should only be used with Debian-based variants.

The image runs as the non-root `py` user with `/workspace` as both its home and working directory. `WORKDIR_PATH` changes that directory. The package is available through `/pkg`, regardless of the installed wheel layout.

The generated entrypoint selects a console script in the following order.

1. The `[project.scripts]` key named by `CONTAINER_CUSTOM_ENTRYPOINT`
2. A script matching the underscore-normalized package name
3. A script matching the hyphenated package name
4. `python`

An explicit `CONTAINER_CUSTOM_ENTRYPOINT` must match a key in `[project.scripts]`. The selected command is fixed at build time and receives the container command as its arguments.

## Container environment declarations

Most `CONTAINER_*` variables are host-side task settings. They control Dockerfile rendering, naming, or build orchestration and are not automatically exposed inside the image.

`CONTAINER_ENV` is different. It accepts `KEY=VALUE` declarations that are rendered as `ENV` instructions in both `builder` and `runtime`. These values are therefore available while the package is built, during later runtime-stage build instructions, and whenever a container starts from the resulting image.

Declarations are accumulated from lowest to highest precedence.

1. The project-root `.containerenv` file
2. Files passed through `--container-envfile`
3. `CONTAINER_ENV`
4. Values passed through `--container-env`

Later declarations with the same key override earlier declarations. Files may use one declaration per line, and inline settings may be colon-delimited. Every declaration must contain `KEY=VALUE`. Quote a value or escape a literal colon as `\:` when it contains a colon.

```text title=".containerenv"
APP_ENV=production
LOG_LEVEL=info
PUBLIC_API_URL="https://api.example.com"
```

```shell
poe build-image --container-env LOG_LEVEL=debug
```

Do not use these declarations for secrets because their values persist in the image configuration. Host variables matching `UV_INDEX_<NAME>_USERNAME` or `UV_INDEX_<NAME>_PASSWORD` are handled separately as BuildKit secrets for uv operations and are not rendered as image environment variables.

The `--env` and `--envfile` options on `run-container` and `container-shell` have ordinary `docker run` semantics. They affect only that container invocation and can override environment values embedded during the build.

## Extending the runtime image

Use `CONTAINER_EXTENSION_FILES` to append project-owned Dockerfile fragments without replacing the generic Dockerfile. Its value is a colon-delimited list of paths, such as `Dockerfile.system:docker/Dockerfile.browser`.

```dockerfile title="Dockerfile.system"
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
USER py
```

Extension files are concatenated in their configured order and inserted near the end of `runtime`, after the entrypoint is created and after `USER py`. An extension that needs elevated permissions must switch to `USER root`; it should normally restore `USER py` for the instructions that follow. `COPY` paths remain relative to the project-root build context.

Extension content is treated as raw Dockerfile syntax, not as a Jinja template. This keeps project extensions independent of private template variables used by `common-python-tasks`.

`CONTAINER_EXTENSIONS` selects extension bundles shipped in the installed package's `data/dockerfile_extensions/` directory. Bundle names are colon-delimited and are applied after local extension files. A bundle may accept one value with `bundle=value`; that value is passed to the first `ARG` declared by the bundle that has not already been assigned to another extension. Arguments are ignored with a warning when the bundle declares no `ARG`.

Use an extension for additive runtime instructions. Use `CONTAINER_DOCKERFILE_HOOK_PATH` only when a change must rewrite another part of the generated Dockerfile. The hook must be an executable host-side script; it receives the generated Dockerfile path as its first argument and must edit that file in place. The hook also receives the following context variables.

| Variable | Meaning |
| - | - |
| `COMMON_PYTHON_TASKS_DOCKERFILE_PATH` | Generated Dockerfile path, matching the first script argument |
| `COMMON_PYTHON_TASKS_DOCKER_CONTEXT` | Docker build context path |
| `COMMON_PYTHON_TASKS_DOCKER_DEBUG` | `1` for a debug build, otherwise `0` |
| `COMMON_PYTHON_TASKS_DOCKER_NO_CACHE` | `1` when `--no-cache` is active, otherwise `0` |
| `COMMON_PYTHON_TASKS_DOCKER_PLAIN` | `1` when plain progress output is active, otherwise `0` |
| `COMMON_PYTHON_TASKS_DOCKER_SINGLE_ARCH` | `1` for a single-architecture build, otherwise `0` |

## Supplying external dependencies

Dependency images support artifacts that should be built separately from the application wheel, such as compiled tools or browser binaries. The dependency image must place its exported content under `/tmp/deps`; the generated application Dockerfile copies that directory into its `runtime` stage.

There are three ways to select the dependency image.

| Setting | Behavior |
| - | - |
| `CONTAINER_DEPS_CONTENT` | Supplies inline instructions appended to the bundled dependency-image Dockerfile. The bundle already defines the base image and creates `/tmp/deps`. |
| `CONTAINER_DEPS_FILE` | Supplies one or more colon-delimited paths to complete dependency Dockerfiles. Multiple files are concatenated in order. |
| `CONTAINER_DEPS_IMAGE` | Reuses an existing image whose artifacts are already in `/tmp/deps`. |

Inline content takes precedence over dependency files. Either local source takes precedence over an existing `CONTAINER_DEPS_IMAGE` because `build-image` builds and tags a content-addressed dependency image first. `build-deps-image` can build that image independently.

After copying `/tmp/deps`, the runtime build can distribute its contents in one of two ways. `CONTAINER_DEPS_MAPPINGS` accepts whitespace-delimited `name:/destination/path` pairs and moves `/tmp/deps/<name>` to each destination. For more control, use an inline `CONTAINER_DEPS_MOVE_SCRIPT` or a file named by `CONTAINER_DEPS_MOVE_SCRIPT_PATH`. A script path takes precedence over an inline script, and either script takes precedence over mappings.

```toml
[tool.poe.env]
CONTAINER_DEPS_IMAGE = "example/toolchain:2026.09"
CONTAINER_DEPS_MAPPINGS = "bin/tool:/usr/local/bin/tool share/tool:/usr/local/share/tool"
```

## Passing Docker build options

Arguments following Poe's `--` separator are passed directly to `docker build` when the task accepts positional Docker arguments.

```shell
poe build-image --single-arch -- --secret id=pip_conf,env=PIP_CONF
```

Set `CONTAINER_DOCKER_BUILD_ARGS` to persist the same options using shell quoting rules. Arguments supplied after `--` replace this setting for that invocation. Managed arguments are emitted before these native Docker arguments, so an explicit option such as `--build-arg WORKDIR_PATH=/app` can override its managed value.

See [Container settings](../configuration.md#container-settings) for the complete settings reference.

<!-- generated-task-reference -->

| Task | Description |
| - | - |
| [`build-image`](reference/build-image.md) | Build the container image for this project using the Dockerfile template. |
| [`build-deps-image`](reference/build-deps-image.md) | Build only the container dependency collector image for this project. |
| [`run-container`](reference/run-container.md) | Run the Docker image as a container for this project. |
| [`push-image`](reference/push-image.md) | Push the Docker image for this project to the container registry. |
| [`build`](reference/build.md) | Build the project and its containers. |
| [`container-shell`](reference/container-shell.md) | Run the debug image with an interactive shell. |

<!-- end-generated-task-reference -->
