# Mac Docker Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver one command that downloads the local Git snapshot from the VM and starts json-pptx in Docker Desktop on the main Mac.

**Architecture:** Package only committed application sources, with SHA-256 and revision metadata. A Mac launcher selects the local `desktop-linux` context, builds through the existing Dockerfile and waits for health. Transfer uses the existing narrow package server from the neighboring Teploshema project.

**Tech Stack:** Python standard library, Bash, Docker Compose v2, existing FastAPI/React Dockerfile.

**Spec:** User instructions in this chat; reference workflow: `/Users/alexander/Projects/teploshema/scripts/docker-mac.sh` and `/Users/alexander/Projects/productframe/docker/README-MAC.md`.

## Global Constraints

- Target is the main Mac with Docker Desktop; source Git is local inside the VM.
- No SSH deployment or remote Git publication is required.
- Preserve runtime data in named volumes and bind the Mac UI to loopback.
- Exclude tracked node_modules, generated frontend files, Requirements and runtime data from delivery.
- Increment APP_VERSION for configuration/script changes; do not change application behavior or the existing server deployment.

## Review Focus

- Docker CLI exists outside PATH: find Docker Desktop and its credential helpers.
- A remote Docker context is selected globally: force and validate local desktop-linux.
- Package contents change after download: fail before invoking Docker.
- Container startup fails: return failure and display logs, never report success.
- Paths contain spaces: package and run using quoted absolute paths.

### Task 1: Reproducible Mac package and launcher

**Files:** Create `scripts/run-mac.sh`, `scripts/package-mac.py`, `docker-compose.mac.yml`, `tests/test_mac_deployment.py`; modify `README.md`, `roadmap_generator/version.py`.

**Interfaces:** `package(repo: Path, output_dir: Path) -> dict` returns archive path, root directory, revision, version and SHA-256. The archive includes `SOURCE_REVISION`, `VERSION` and `SHA256SUMS`. `bash scripts/run-mac.sh start` verifies the package, builds and starts it; `check`, `verify`, `status`, `logs`, `stop` support repeat use.

- [x] Write tests for source selection, dirty Git refusal, package tampering, local context selection and failed startup. Run them and confirm feature-absence failures.
- [x] Implement package export and launcher; run the deployment tests and shell syntax checks.
- [x] Run applicable backend checks and frontend typecheck/build with isolated toolchains. Result: 196 passed on Python 3.14.10 (one third-party deprecation warning); frontend typecheck/build passed. A fresh review found partial output on failed exports; fixed with a RED/GREEN regression test. The main Mac Docker engine is not accessible from this VM.
- [ ] Review the diff, commit only this task locally, package that clean revision and verify extraction/checksums.
- [ ] Start the existing single-file transfer server on the VM IPv4; download the served archive and compare SHA-256. Give the exact host command.

Rollback: stop the Mac Compose project with the supplied launcher; named volumes remain. Revert the local commit to remove source changes. No remote deployment is performed by the VM.

Delivery evidence is generated after the clean commit in `../releases/`: package metadata, transfer metadata, checksums and the exact main Mac command. The source package builds the image on the main Mac; it does not claim an already verified Docker image.
