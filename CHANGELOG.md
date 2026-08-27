## [0.10.1] - 2026-08-27

### 🐛 Bug Fixes

- Missing artifacts before image build during release

### ⚙️ Miscellaneous Tasks

- *(release)* Set README version 0.10.1

## [0.10.0] - 2026-08-20

### 🚀 Features

- Add support for UV index credentials and Python variant in Docker builds

### 🐛 Bug Fixes

- Formatting; `PYTHON_VARIANT`

### ⚙️ Miscellaneous Tasks

- *(release)* Set README version 0.10.0

## [0.9.0] - 2026-08-19

### 🚀 Features

- Avoid hidden paths in GitHub release asset processing
- Add publish target selection and environment variable fallbacks for package publishing
- [**breaking**] Drop Poetry support

### ⚙️ Miscellaneous Tasks

- *(release)* Set README version 0.9.0

## [0.8.0] - 2026-08-15

### 🚀 Features

- Enhance bundled ruff config
- Add task table update task
- [**breaking**] Standardize container configuration and task argument passing

### 🐛 Bug Fixes

- *(docker)* Clean temporary Dockerfiles on failure
- *(errors)* Interpolate fatal messages
- *(fastapi)* Share container build and cleanup lifecycle

### 🚜 Refactor

- *(env)* Remove redundant delimiter helper
- *(git)* Centralize branch discovery

### 📚 Documentation

- *(api)* Complete public function docstrings

### ⚙️ Miscellaneous Tasks

- *(docs)* Refresh README task table
- Update gitignore
- *(release)* Set README version 0.8.0

## [0.7.0] - 2026-08-03

### 🐛 Bug Fixes

- Less verbosity

### 💼 Other

- Formatting

### 🚜 Refactor

- [**breaking**] Replace `black` and `isort` with `ruff` for formatting and linting

### 📚 Documentation

- Reorder some sections

### ⚙️ Miscellaneous Tasks

- *(release)* Set README version 0.7.0

## [0.6.0] - 2026-07-30

### 🚀 Features

- Add options to publish to different repositories
- Add package manager update command

### ⚙️ Miscellaneous Tasks

- *(release)* Set README version 0.6.0

## [0.5.1] - 2026-07-07

### 🐛 Bug Fixes

- GH Releases empty asset list

### ⚙️ Miscellaneous Tasks

- *(release)* Set README version 0.5.1

## [0.5.0] - 2026-07-07

### 🚀 Features

- Enhance container entrypoint resolution with custom script validation
- *(containers)* Validate custom entrypoint scripts (#19)
- Replace shell script installer with Python installer
- Utilize LRU cache for GitHub stuff

### 🐛 Bug Fixes

- Update vscode settings
- Make a log debug
- Fix broken `APT_PACKAGES`
- *(github)* Make cached configuration environment-aware

### 💼 Other

- Formatting

### ⚙️ Miscellaneous Tasks

- *(release)* Set README version 0.5.0

## [0.4.1] - 2026-06-16

### 🚀 Features

- `uv` support

### ⚙️ Miscellaneous Tasks

- *(release)* Set README version 0.4.1

## [0.4.0] - 2026-06-15

### 🚀 Features

- Add support for git-less testing
- Add `get_black_target_version` to avoid compatibility warning
- Add `build-deps-image` task
- Enhance Docker image handling for any container registry
- Update registry username handling/container registry URL logic
- Allow passing specific test file paths to `test`
- Make var positional task args optional

### 🐛 Bug Fixes

- Fix broken `build_deps_image_task`
- Update `build_image` references to fix broken release stuff
- [**breaking**] `REGISTRY_USERNAME` -> `CONTAINER_REGISTRY_USERNAME`
- Add 'enable' value to `TRUTHY_VALUES`

### 💼 Other

- Wording
- Remove useless dupe dep
- Remove unnecessary fields from project examples

### 🚜 Refactor

- *(env)* [**breaking**] Unify shell-style parsing for colon-delimited env vars
- Compute version outside `build-image` task

### 📚 Documentation

- README formatting
- Update README

### ⚙️ Miscellaneous Tasks

- *(release)* Set README version 0.4.0

## [0.3.1] - 2026-05-26

### 🐛 Bug Fixes

- Auto-add newlines to changelog

### 💼 Other

- Add newline to changelog

### 🚜 Refactor

- Improve type hints and error handling in utility functions
- Remove `ReleaseComponentBump`
- Add `git cliff` data file and correctly version bump pre-1.0.0 releases

### ⚙️ Miscellaneous Tasks

- *(release)* Set README version 0.3.1

## [0.3.0] - 2026-05-22

### 🐛 Bug Fixes

- *(release)* Remove useless post-release phase
- *(release)* `git push` as necessary
- *(release)* Resolve release phase during main execution
- *(tests)* Fix broken release tests
- Fix log regression
- Remove "unreleased" section from `git-cliff` output
- *(tests)* Fix tests for changelog

### 💼 Other

- Add newline to changelog

### 🚜 Refactor

- [**breaking**] Refactor several functions for less redundant code, use of enums, etc.; update tests

### ⚙️ Miscellaneous Tasks

- *(dependabot)* Remove dependabot as "widen" is not yet supported for Python
- *(release)* Set README version 0.3.0

## [0.2.0] - 2026-05-21

### 🚀 Features

- *(github)* Allow `get_github_token` to retrieve token from GitHub CLI if available

### 🐛 Bug Fixes

- *(dependabot)* `widen` for dependabot
- *(tests)* Remove "[DRY RUN]" from output assertions
- Properly replace README version references

### ⚙️ Miscellaneous Tasks

- *(release)* Set README version 0.2.0

## [0.1.0] - 2026-05-10

### 🚀 Features

- Add fallback to latest tagged release notes when unreleased placeholder is detected
- Add release script to update README
- Add cache to more stuff
- Add better logging for tasks-in-tasks
- Update release pre-script for keeping tasks in check
- [**breaking**] Common defaults
- Tweak release script to use a placeholder (and consequently add a post script)
- Enhance version computation flow
- Fix `PYTHONPATH` in `tool.poe.env`
- Implement dry-run functionality for release scripts
- Add changelog management for releases
- Log formatting in release script
- Log formatting in release script

### 🐛 Bug Fixes

- Typo in tests
- Handle optional config paths for `isort` and `flake8`
- Exclude 'containers' tag in this project
- Remove useless file
- Add environment variable fixtures for tests
- Include `--unreleased` flag in `git cliff`
- Color log

### 💼 Other

- Remove unnecessary log
- Remove unnecessary param and logs

### 🚜 Refactor

- Clean up release flow; add back `dry_run` params
- Update release script to use `RELEASE_SCRIPT_PHASE` env var
- Logging for changelog

### 📚 Documentation

- Update README
- Clarify needing `PYTHONPATH` set for development

### 🧪 Testing

- Add tests for prepend_changelog utility function
- Add new tests for dotenv and entrypoint command resolution

### ⚙️ Miscellaneous Tasks

- Update version in README
- Remove usless item after all in `pyproject.toml`
- *(release)* Set README version 0.1.0

# Changelog

## [Unreleased]
