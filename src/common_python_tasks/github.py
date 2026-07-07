import json
import logging
import mimetypes
import os
import re
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import requests

from . import utils
from .env import env_truthy
from .utils import changelog as _changelog

LOGGER = logging.getLogger(__name__)

GitHubEndpoint = Literal["api", "uploads"]


def _is_unreleased_placeholder(notes: str) -> bool:
    normalized_lines = [line.strip() for line in notes.splitlines() if line.strip()]
    if not normalized_lines:
        return True

    normalized = "\n".join(normalized_lines).lower()
    return normalized in {"[unreleased]", "## [unreleased]", "## unreleased"}


def _latest_tagged_changelog() -> str | None:
    result = utils.run_git_cliff(["--latest"], capture_output=True)
    changelog = result.stdout.strip()
    if not changelog:
        LOGGER.warning("git-cliff produced no release notes for the latest tag")
        return None
    return changelog


def should_publish_github_release() -> bool:
    """Return whether GitHub Releases publication is enabled.

    Returns:
        `True` if GitHub Release publishing is enabled, `False` if it is skipped.
    """
    return not env_truthy("SKIP_GITHUB_RELEASE")


def get_github_repository() -> str | None:
    """Return the GitHub repository slug for the current project if available.

    Returns:
        The GitHub repository slug in the form `owner/repo`, or `None` if it
        cannot be determined.
    """
    return _get_github_repository(
        os.getenv("GITHUB_REPOSITORY", "").strip(),
        Path.cwd(),
        utils.run_command,
    )


@lru_cache(maxsize=32)
def _get_github_repository(
    repository: str,
    _working_directory: Path,
    run_command: Callable[..., Any],
) -> str | None:
    if repository:
        if re.fullmatch(r"[^/]+/[^/]+", repository):
            return repository
        LOGGER.warning("Ignoring invalid GITHUB_REPOSITORY value: %s", repository)

    result = run_command(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        acceptable_returncodes={0, 128},
    )
    if result.returncode != 0:
        return None

    remote_url = result.stdout.strip()
    if not remote_url:
        return None

    for pattern in (
        r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$",
        r"^ssh://git@github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$",
        r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
    ):
        match = re.match(pattern, remote_url)
        if match:
            return f"{match.group('owner')}/{match.group('repo')}"

    return None


def get_github_token() -> str | None:
    """Return the GitHub token used for API requests. Check the following in order:
    1. `GITHUB_TOKEN` environment variable
    2. `GH_TOKEN` environment variable
    3. GitHub CLI via `gh auth token`

    Returns:
        The GitHub token or `None` if it cannot be found.
    """
    token = (os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or "").strip()
    if token:
        return token

    return _get_github_cli_token(utils.run_command)


@lru_cache(maxsize=8)
def _get_github_cli_token(run_command: Callable[..., Any]) -> str | None:
    try:
        result = run_command(
            ["gh", "auth", "token"],
            capture_output=True,
            acceptable_returncodes={0, 1},
        )
    except FileNotFoundError:
        LOGGER.warning(
            "GitHub CLI not installed; cannot retrieve token via `gh auth token`"
        )
        return None

    if result is None:
        return None

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        message = "Failed to retrieve GitHub token via `gh auth token`"
        if stderr:
            message += f": {stderr}"
        LOGGER.warning(message)
        return None

    token = (result.stdout or "").strip()
    if not token:
        LOGGER.warning("`gh auth token` returned an empty token")
        return None

    return token


def get_github_api_base_url() -> str:
    """Return the GitHub API base URL.

    Returns:
        The base URL for GitHub API requests, defaulting to GitHub.com API or
        GitHub Enterprise API if configured.
    """
    return _get_github_api_base_url(
        os.getenv("GITHUB_API_URL", "").strip(),
        os.getenv("GITHUB_SERVER_URL", "https://github.com").strip(),
    )


@lru_cache(maxsize=32)
def _get_github_api_base_url(api_url: str, server_url: str) -> str:
    if api_url:
        return api_url.rstrip("/")

    server_url = server_url.rstrip("/")
    if server_url.endswith("github.com"):
        return "https://api.github.com"
    return f"{server_url}/api/v3"


def get_github_upload_api_base_url(api_base_url: str | None = None) -> str:
    """Return the GitHub upload API base URL.

    For GitHub.com uploads, this is a dedicated uploads host. For Enterprise
    installations, use the same API base URL.

    Args:
        api_base_url: Optional precomputed API base URL.

    Returns:
        The upload base URL for GitHub API requests.
    """
    return _get_github_upload_api_base_url(api_base_url or get_github_api_base_url())


@lru_cache(maxsize=32)
def _get_github_upload_api_base_url(api_base: str) -> str:
    if api_base == "https://api.github.com":
        return "https://uploads.github.com"
    return api_base


class GitHubClient:
    """Encapsulate GitHub API and upload request behavior."""

    def __init__(self, repository: str | None = None, token: str | None = None):
        """Create a GitHub API client.

        Args:
            repository: Optional repository slug (owner/repo). If not provided
                it will be inferred from git remotes.
            token: Optional GitHub token. If not provided it will be read from
                environment variables.
        """
        if repository is None:
            repository = get_github_repository()
        if token is None:
            token = get_github_token()

        self.repository = repository
        self.token = token
        api_base_url = get_github_api_base_url()
        self.endpoint_base_urls: dict[GitHubEndpoint, str] = {
            "api": api_base_url,
            "uploads": get_github_upload_api_base_url(api_base_url),
        }

    @property
    def is_available(self) -> bool:
        """Whether the client has sufficient information to make authenticated API requests."""
        return self.repository is not None and self.token is not None

    def _build_headers(self, content_type: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "common-python-tasks",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if content_type is not None:
            headers["Content-Type"] = content_type
        return headers

    def _get_base_url(self, endpoint: GitHubEndpoint) -> str:
        return self.endpoint_base_urls[endpoint]

    def _build_url(self, path: str, endpoint: GitHubEndpoint = "api") -> str:
        return f"{self._get_base_url(endpoint)}/repos/{self.repository}{path}"

    def _request(
        self,
        method: str,
        path: str,
        payload: bytes | None = None,
        endpoint: GitHubEndpoint = "api",
        content_type: str | None = None,
        allow_404: bool = False,
        token_required: bool = False,
    ) -> dict[str, Any] | None:
        if self.repository is None:
            return None
        if self.token is None:
            if token_required:
                utils.fatal(
                    "An API token must be passed to publish GitHub Release assets"
                )
            return None

        response = requests.request(
            method=method,
            url=self._build_url(path, endpoint=endpoint),
            data=payload,
            headers=self._build_headers(content_type),
            timeout=30,
        )

        if allow_404 and response.status_code == 404:
            return None
        response.raise_for_status()

        body = response.text.strip()
        if not body:
            return None
        return response.json()

    def api_request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        allow_404: bool = False,
    ) -> dict[str, Any] | None:
        request_payload = (
            None if payload is None else json.dumps(payload).encode("utf-8")
        )
        content_type = "application/json" if payload is not None else None
        return self._request(
            method,
            path,
            payload=request_payload,
            endpoint="api",
            content_type=content_type,
            allow_404=allow_404,
        )

    def upload_request(
        self,
        method: str,
        path: str,
        payload: bytes | None = None,
        content_type: str | None = None,
    ) -> dict[str, Any] | None:
        """Perform a GitHub upload request and decode the JSON response.

        Args:
            method: HTTP method name (e.g. 'POST', 'DELETE').
            path: API path relative to the repository.
            payload: Optional raw bytes to upload as the request body.
            content_type: Optional MIME type for the request body.

        Returns:
            The decoded JSON response as a dictionary, or `None` when there is
            no response body.
        """

        if content_type is None and payload is not None:
            content_type = "application/octet-stream"
        return self._request(
            method,
            path,
            payload=payload,
            endpoint="uploads",
            content_type=content_type,
            token_required=True,
        )


def github_api_request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Perform a GitHub API request and return the decoded JSON response.

    Args:
        method: HTTP method (e.g. `GET`, `POST`, `PATCH`).
        path: API path relative to `/repos/{owner}/{repo}`.
        payload: Optional JSON-serialisable request body.

    Returns:
        Parsed JSON response body, or `None` if there is no body or the
        required credentials are unavailable.
    """
    return GitHubClient().api_request(method, path, payload=payload)


def publish_github_release(
    tag_name: str,
    release_name: str | None = None,
    body: str | None = None,
    prerelease: bool = False,
    draft: bool = False,
    assets: list[Path | str] | None = None,
) -> dict[str, Any] | None:
    """Create or update a GitHub Release for the given tag.

    Args:
        tag_name: Git tag name for this release.
        release_name: Display name of the release. Defaults to `tag_name`.
        body: Release description text. Defaults to `Release {tag_name}`.
        prerelease: Mark the release as a pre-release.
        draft: Mark the release as a draft.
        assets: Optional list of paths to upload as release assets.

    Returns:
        The GitHub API response for the created or updated release, or `None`
        when publication is disabled or credentials are unavailable.
    """
    if not should_publish_github_release():
        LOGGER.debug(
            "Skipping GitHub Release publication because SKIP_GITHUB_RELEASE is set"
        )
        return None

    repository = get_github_repository()
    token = get_github_token()

    if repository is None:
        LOGGER.debug(
            "Skipping GitHub Release publication because this is not a GitHub repository"
        )
        return None
    if token is None:
        utils.fatal(
            "GITHUB_TOKEN or GH_TOKEN environment variable must be set to publish GitHub Release"
        )

    release_name = release_name or tag_name
    release_body = body if body is not None else _changelog()
    if release_body is not None and _is_unreleased_placeholder(release_body):
        LOGGER.info(
            "git-cliff returned an unreleased placeholder; using latest tagged release notes instead"
        )
        release_body = _latest_tagged_changelog()
    if release_body is None:
        release_body = f"Release {tag_name}"

    payload = {
        "tag_name": tag_name,
        "name": release_name,
        "body": release_body,
        "draft": draft,
        "prerelease": prerelease,
    }

    client = GitHubClient(repository=repository, token=token)
    encoded_tag_name = requests.utils.quote(tag_name, safe="")
    existing_release = client.api_request(
        "GET",
        f"/releases/tags/{encoded_tag_name}",
        allow_404=True,
    )
    if existing_release and isinstance(existing_release.get("id"), int):
        LOGGER.info("Updating GitHub Release for tag %s", tag_name)
        release = client.api_request(
            "PATCH",
            f"/releases/{existing_release['id']}",
            payload=payload,
        )
    else:
        LOGGER.info("Creating GitHub Release for tag %s", tag_name)
        release = client.api_request("POST", "/releases", payload=payload)

    if assets is None:
        assets = get_github_release_asset_paths()
    assets_to_upload = [
        Path(asset) if not isinstance(asset, Path) else asset for asset in assets
    ]
    if assets_to_upload:
        if release is None or not isinstance(release.get("id"), int):
            utils.fatal(
                "GitHub Release was not created successfully; cannot upload assets."
            )
        upload_github_release_assets(release["id"], assets_to_upload)
    else:
        LOGGER.info("No GitHub Release assets found to upload for tag %s", tag_name)

    return release


def github_upload_request(
    method: str,
    path: str,
    payload: bytes | None = None,
    content_type: str | None = None,
) -> dict[str, Any] | None:
    """Perform a GitHub upload request and return the decoded JSON response.

    Args:
        method: HTTP method (e.g. `POST`, `DELETE`).
        path: API path relative to `/repos/{owner}/{repo}`.
        payload: Optional raw bytes to upload as the request body.
        content_type: Optional MIME type of the uploaded content. Defaults to
            `application/octet-stream` when `payload` is provided.

    Returns:
        The decoded JSON response from the GitHub API, or `None` if the request
        fails.
    """

    return GitHubClient().upload_request(
        method,
        path,
        payload=payload,
        content_type=content_type,
    )


def get_github_release_asset_paths(
    asset_sources: str | list[str] | None = None,
) -> list[Path]:
    """Return asset paths to upload for a GitHub Release.

    Args:
        asset_sources: Optional list of paths or glob patterns. When a string is
            provided (including via `GITHUB_RELEASE_ASSETS`), values are
            interpreted as colon-separated paths or glob patterns.
            If not provided, the default value is `dist/*`. An empty list
            explicitly disables asset selection.

    Returns:
        A sorted list of existing asset paths.
    """
    from .env import split_colon_delimited_values

    if asset_sources is not None:
        explicit_assets = True
        if isinstance(asset_sources, list):
            source_items = [item.strip() for item in asset_sources if item.strip()]
        else:
            source_items = split_colon_delimited_values(asset_sources)
    else:
        env_asset_sources = os.getenv("GITHUB_RELEASE_ASSETS")
        explicit_assets = bool(env_asset_sources)
        if env_asset_sources:
            source_items = split_colon_delimited_values(env_asset_sources)
        else:
            source_items = ["dist/*"]

    asset_paths: list[Path] = []
    for part in source_items:
        if any(char in part for char in "*?[]"):
            asset_paths.extend(
                sorted(
                    [path for path in Path(".").glob(part) if path.is_file()],
                    key=lambda p: str(p),
                )
            )
            continue

        path = Path(part)
        if path.is_file():
            asset_paths.append(path)
        elif path.exists():
            LOGGER.warning("Ignoring non-file GitHub release asset path: %s", path)

    if not asset_paths and explicit_assets and source_items:
        utils.fatal(
            "No GitHub Release assets were found for the configured asset paths: "
            + ":".join(source_items)
        )

    return sorted(dict.fromkeys(asset_paths), key=lambda p: str(p))


def get_github_release_assets(release_id: int) -> list[dict[str, Any]]:
    """Get existing assets for a GitHub Release.

    Args:
        release_id: The numeric ID of the GitHub Release.

    Returns:
        A list of asset dictionaries as returned by the GitHub API.
    """
    return github_api_request("GET", f"/releases/{release_id}/assets") or []


def delete_github_release_asset(asset_id: int) -> None:
    """Delete a GitHub Release asset by ID.

    Args:
        asset_id: The numeric ID of the asset to delete.
    """
    github_upload_request("DELETE", f"/releases/assets/{asset_id}")


def upload_github_release_asset(
    release_id: int, asset_path: Path
) -> dict[str, Any] | None:
    """Upload a single asset to a GitHub Release.

    Args:
        release_id: The numeric ID of the release to upload to.
        asset_path: Path to the file to upload.

    Returns:
        The decoded JSON response for the uploaded asset, or `None` on failure.
    """

    if not asset_path.is_file():
        utils.fatal("GitHub Release asset not found: %s", asset_path)

    existing_assets = get_github_release_assets(release_id)
    for asset in existing_assets:
        if asset.get("name") == asset_path.name and isinstance(asset.get("id"), int):
            LOGGER.info("Deleting existing GitHub release asset %s", asset_path.name)
            delete_github_release_asset(asset["id"])
            break

    content_type, _ = mimetypes.guess_type(str(asset_path))
    content_type = content_type or "application/octet-stream"
    return github_upload_request(
        "POST",
        f"/releases/{release_id}/assets?name={requests.utils.quote(asset_path.name, safe='')}",
        payload=asset_path.read_bytes(),
        content_type=content_type,
    )


def upload_github_release_assets(
    release_id: int, asset_paths: list[Path]
) -> list[dict[str, Any]]:
    """Upload multiple assets to a GitHub Release.

    Args:
        release_id: The numeric ID of the release to upload to.
        asset_paths: A list of Paths to files to upload as assets.

    Returns:
        A list of decoded JSON responses for the uploaded assets.
    """
    uploaded_assets: list[dict[str, Any]] = []
    for asset_path in asset_paths:
        LOGGER.info("Uploading GitHub Release asset: %s", asset_path)
        uploaded = upload_github_release_asset(release_id, asset_path)
        if uploaded is not None:
            uploaded_assets.append(uploaded)
    return uploaded_assets
