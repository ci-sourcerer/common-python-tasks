import json
import logging
import mimetypes
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from common_python_tasks.utils import changelog as _changelog

from . import utils
from .env import env_truthy

LOGGER = logging.getLogger(__name__)


def should_publish_github_release() -> bool:
    """Return whether GitHub Releases publication is enabled.

    Returns:
        True if GitHub Release publishing is enabled, False if it is skipped.
    """
    return not env_truthy("SKIP_GITHUB_RELEASE")


def get_github_repository() -> str | None:
    """Return the GitHub repository slug for the current project if available.

    Returns:
        The GitHub repository slug in the form `owner/repo`, or `None` if it
        cannot be determined.
    """
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    if repository:
        if re.fullmatch(r"[^/]+/[^/]+", repository):
            return repository
        LOGGER.warning("Ignoring invalid GITHUB_REPOSITORY value: %s", repository)

    result = utils.run_command(
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
    """Return the GitHub token used for API requests.

    Returns:
        The GitHub token from `GITHUB_TOKEN` or `GH_TOKEN`, or `None` if unset.
    """
    return (os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or "").strip() or None


def get_github_api_base_url() -> str:
    """Return the GitHub API base URL.

    Returns:
        The base URL for GitHub API requests, defaulting to GitHub.com API or
        GitHub Enterprise API if configured.
    """
    api_url = os.getenv("GITHUB_API_URL", "").strip()
    if api_url:
        return api_url.rstrip("/")

    server_url = (
        os.getenv("GITHUB_SERVER_URL", "https://github.com").strip().rstrip("/")
    )
    if server_url.endswith("github.com"):
        return "https://api.github.com"
    return f"{server_url}/api/v3"


def get_github_upload_api_base_url() -> str:
    """Return the GitHub upload API base URL.

    For GitHub.com uploads, this is a dedicated uploads host. For Enterprise
    installations, use the same API base URL.
    """
    api_base = get_github_api_base_url()
    if api_base == "https://api.github.com":
        return "https://uploads.github.com"
    return api_base


class GitHubClient:
    """Encapsulate GitHub API and upload request behavior."""

    def __init__(self, repository: str | None = None, token: str | None = None):
        if repository is None:
            repository = get_github_repository()
        if token is None:
            token = get_github_token()

        self.repository = repository
        self.token = token

    @property
    def is_available(self) -> bool:
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

    def _build_url(self, path: str, upload: bool = False) -> str:
        base_url = (
            get_github_upload_api_base_url() if upload else get_github_api_base_url()
        )
        return f"{base_url}/repos/{self.repository}{path}"

    def _request(
        self,
        method: str,
        path: str,
        payload: bytes | None = None,
        upload: bool = False,
        content_type: str | None = None,
        allow_404_release_tag: bool = False,
    ) -> dict[str, Any] | None:

        if self.repository is None:
            return None
        if self.token is None:
            if upload:
                utils.fatal(
                    "GITHUB_TOKEN or GH_TOKEN environment variable must be set to publish GitHub Release assets"
                )
            return None

        request = urllib.request.Request(
            self._build_url(path, upload=upload),
            data=payload,
            method=method,
            headers=self._build_headers(content_type),
        )

        try:
            with urllib.request.urlopen(request) as response:
                body = response.read().decode("utf-8").strip()
        except urllib.error.HTTPError as exc:
            if (
                allow_404_release_tag
                and method == "GET"
                and exc.code == 404
                and path.startswith("/releases/tags/")
            ):
                return None
            raise

        if not body:
            return None
        return json.loads(body)

    def api_request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        allow_404_release_tag: bool = False,
    ) -> dict[str, Any] | None:
        request_payload = (
            None if payload is None else json.dumps(payload).encode("utf-8")
        )
        content_type = "application/json" if payload is not None else None
        return self._request(
            method,
            path,
            payload=request_payload,
            upload=False,
            content_type=content_type,
            allow_404_release_tag=allow_404_release_tag,
        )

    def upload_request(
        self,
        method: str,
        path: str,
        payload: bytes | None = None,
        content_type: str | None = None,
    ) -> dict[str, Any] | None:
        if content_type is None and payload is not None:
            content_type = "application/octet-stream"
        return self._request(
            method,
            path,
            payload=payload,
            upload=True,
            content_type=content_type,
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
    encoded_tag_name = urllib.parse.quote(tag_name, safe="")
    existing_release = client.api_request(
        "GET",
        f"/releases/tags/{encoded_tag_name}",
        allow_404_release_tag=True,
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
    """Perform a GitHub upload request and return the decoded JSON response."""
    return GitHubClient().upload_request(
        method,
        path,
        payload=payload,
        content_type=content_type,
    )


def get_github_release_asset_paths(asset_sources: str | None = None) -> list[Path]:
    """Return asset paths to upload for a GitHub Release.

    Args:
        asset_sources: Optional colon-separated list of paths or glob patterns.
            If not provided, the default value is `dist/*`.

    Returns:
        A sorted list of existing asset paths.
    """

    sources = (
        asset_sources
        if asset_sources is not None
        else os.getenv("GITHUB_RELEASE_ASSETS", "dist/*")
    )
    explicit_assets = asset_sources is not None or os.getenv("GITHUB_RELEASE_ASSETS")

    asset_paths: list[Path] = []
    for part in (p.strip() for p in sources.split(":") if p.strip()):
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

    if not asset_paths and explicit_assets:
        utils.fatal(
            f"No GitHub Release assets were found for the configured asset paths: {sources}"
        )

    return sorted(dict.fromkeys(asset_paths), key=lambda p: str(p))


def get_github_release_assets(release_id: int) -> list[dict[str, Any]]:
    """Get existing assets for a GitHub Release."""
    return github_api_request("GET", f"/releases/{release_id}/assets") or []


def delete_github_release_asset(asset_id: int) -> None:
    """Delete a GitHub Release asset by ID."""
    github_upload_request("DELETE", f"/releases/assets/{asset_id}")


def upload_github_release_asset(
    release_id: int, asset_path: Path
) -> dict[str, Any] | None:
    """Upload a single asset to a GitHub Release."""
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
        f"/releases/{release_id}/assets?name={urllib.parse.quote(asset_path.name, safe='')}",
        payload=asset_path.read_bytes(),
        content_type=content_type,
    )


def upload_github_release_assets(
    release_id: int, asset_paths: list[Path]
) -> list[dict[str, Any]]:
    """Upload multiple assets to a GitHub Release."""
    uploaded_assets: list[dict[str, Any]] = []
    for asset_path in asset_paths:
        LOGGER.info("Uploading GitHub Release asset: %s", asset_path)
        uploaded = upload_github_release_asset(release_id, asset_path)
        if uploaded is not None:
            uploaded_assets.append(uploaded)
    return uploaded_assets
