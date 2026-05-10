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
