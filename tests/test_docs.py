import tomllib
from pathlib import Path


def test_zensical_site_has_expected_pages():
    with Path("zensical.toml").open("rb") as config_file:
        zensical_config = tomllib.load(config_file)

    assert zensical_config["project"]["site_name"] == "Common Python Tasks"
    # nav is auto-generated from the file structure, so we don't check it explicitly
    assert all(
        Path("docs", page).is_file()
        for page in [
            "index.md",
            "getting-started.md",
            "tasks/index.md",
            "tasks/daily-development.md",
            "tasks/documentation.md",
            "tasks/packaging-and-releases.md",
            "tasks/container-images.md",
            "tasks/development-stacks.md",
            "configuration.md",
            "documentation-workflows.md",
        ]
    )
    # Verify reference directory and some individual task pages exist
    assert Path("docs/tasks/reference").is_dir()
    assert Path("docs/tasks/reference/test.md").is_file()
    assert Path("docs/tasks/reference/build-image.md").is_file()


def test_reusable_docs_workflow_supports_artifacts_and_publishers():
    workflow = Path(".github/workflows/docs.yml").read_text(encoding="utf-8")

    assert "workflow_call:" in workflow
    assert "generated_docs_check_task:" in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "if-no-files-found: error" in workflow
    assert "cloudflare/wrangler-action@v4" in workflow
    assert "--branch=pr-${{ github.event.pull_request.number }}" in workflow
    assert "Ensure Cloudflare Pages project" in workflow
    assert (
        "github.event.pull_request.head.repo.full_name == github.repository" in workflow
    )
    assert "actions/upload-pages-artifact@v5" in workflow
    assert "actions/deploy-pages@v5" in workflow


def test_repository_uses_reusable_docs_workflow():
    preview_workflow = Path(".github/workflows/docs-preview.yml").read_text(
        encoding="utf-8"
    )
    deploy_workflow = Path(".github/workflows/docs-deploy.yml").read_text(
        encoding="utf-8"
    )

    assert "uses: ./.github/workflows/docs.yml" in preview_workflow
    assert "publish_cloudflare:" in preview_workflow
    assert (
        "cloudflare_project_name: ci-sourcerer-common-python-tasks" in preview_workflow
    )
    assert (
        "cloudflare_preview_domain: common-python-tasks.ci-sourcerer.com"
        in preview_workflow
    )
    assert "cloudflare_preview_zone: ci-sourcerer.com" in preview_workflow
    assert "generated_docs_check_task: check-docs-references" in preview_workflow
    assert "uses: ./.github/workflows/docs.yml" in deploy_workflow
    assert "deploy_github_pages: true" in deploy_workflow
    assert "generated_docs_check_task: check-docs-references" in deploy_workflow
    cleanup_workflow = Path(".github/workflows/docs-preview-cleanup.yml").read_text(
        encoding="utf-8"
    )
    assert "types:" in cleanup_workflow
    assert "- closed" in cleanup_workflow
    assert (
        "CLOUDFLARE_PREVIEW_BRANCH: pr-${{ github.event.pull_request.number }}"
        in cleanup_workflow
    )
    assert '"$project_url/deployments/$deployment_id?force=true"' in cleanup_workflow
    assert (
        "CLOUDFLARE_PREVIEW_DOMAIN: common-python-tasks.ci-sourcerer.com"
        in cleanup_workflow
    )
    assert "CLOUDFLARE_PREVIEW_ZONE: ci-sourcerer.com" in cleanup_workflow
