# Unix server container delivery

Goal: package the existing json-pptx application for a conventional Linux
server and publish the result to its existing private GitHub repository.
The user selected the main application and authorized packaging and publication.

Design: keep the existing multi-stage Docker build and single FastAPI process.
Build natively on Linux amd64 or arm64 with Docker Engine and Compose v2.
Keep both named volumes and their existing mountpoints. Bind to localhost by
default, with environment overrides for a trusted LAN. No API or PPTX behavior
changes. No deployment to an existing production server or merge into main.

The existing source-build approach avoids registry credentials and is suitable
for an ordinary server. The Mac-specific ARM64 archive remains separate.
A prebuilt registry image would require an additional publication destination.

Implementation:
- Update Docker/Compose and build-context exclusions; increment APP_VERSION.
- Document installation, configuration, backup, update and rollback.
- Add isolated container smoke checks for UI, API, RU/EN PPTX and persistence.
- Run existing tests/build, review changes and publish a feature branch.
- Run Docker smoke checks on native amd64/arm64 GitHub runners if available.

Verification: pytest, frontend typecheck/build, shell syntax, git diff --check;
real container execution in CI. Never claim runtime verification from static
checks. Tests use disposable Compose projects and synthetic data only.

Rollback: return to the prior Git revision and rebuild; keep both data volumes.
Take a cold backup before updates. Changing the Compose project directory/name
changes volume names, so upgrades must retain that identity.
