# Remove CSV Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Completely remove CSV import and CSV-dependent reports while retaining reports derived from JSON.

**Architecture:** Remove the upload route, parser, frontend state, UI and API types. Keep build_json_report and the annual/English-name reports; remove CSV-only CSS and rename styles still used by the English-name report.

**Tech Stack:** FastAPI, Python, React, TypeScript, Vite, pytest.

**Spec:** `docs/superpowers/specs/2026-11-13-remove-csv-reports-design.md` (approved scope from the user's confirmation).

## Global Constraints

- Preserve JSON/project/profile formats and RU/EN PPTX generation, including Title fallback.
- Preserve annual reports for 2026/2027, TrDate selection, release diagnostics and English-name checks.
- Do not modify Docker, infrastructure, scripts/deploy.sh or user data.
- Work from 3106e635c8d3f54cbc5c87082cb969bfb34682aa on fix/remove-csv-reports; version 1.24.4.

## Review Focus

- CSV UI state must not leave refresh calls behind when JSON/project/session changes.
- Styles shared with the English-name report must survive CSV CSS removal.
- Annual reports and English-name issues must remain independent of a file upload.
- Removing multipart CSV handling must preserve other upload routes.
- CSV publication blocklists are safeguards, not the removed import feature.

### Task 1: Remove CSV import end to end

**Files:**
- Modify: app.py, roadmap_generator/reports.py, roadmap_generator/version.py, roadmap_generator/release_log.py.
- Modify: frontend/src/App.tsx, frontend/src/App.css, frontend/src/api.ts, frontend/src/types.ts.
- Modify: tests/test_reports.py, README.md, AGENTS.md.

**Interfaces:**
- Consumes: current JSON through POST /api/plan and build_json_report(data: list[dict]).
- Produces: unchanged JSON reports; POST /api/reports/public-features no longer processes uploads or appears in OpenAPI.

- [x] **Step 1:** Add test_csv_upload_api_is_removed using a valid multipart upload; assert status 404/405 and no OpenAPI path. Add a RU/EN test for annual reports directly from POST /api/plan without CSV.
- [x] **Step 2:** Run the removed-upload regression alone and verify it fails because the endpoint still accepts CSV.
- [x] **Step 3:** Delete the CSV route and CSV-only helpers, imports, UI, state, response types, client function and CSS. Preserve shared English-report styles with descriptive class names. Delete obsolete CSV tests and their helpers.
- [x] **Step 4:** Remove positive CSV requirements from README.md and AGENTS.md, update APP_VERSION to 1.24.4 and add a release-log entry.
- [x] **Step 5:** Run pytest -q, npm run typecheck and npm run build. Render the actual ReportsDashboard for RU/EN and check retained reports, ENG matches/empty state and absence of upload controls. Run a real-input JSON/PPTX smoke test for RU/EN.
  Expected: all checks pass; no CSV upload controls or active CSV implementation remains.
- [x] **Step 6:** Review the diff, commit, obtain an independent whole-branch review and hand off the checked branch. Rollback is git revert of the removal commit.

## Verification

- CSV removal regression first failed against the original endpoint (HTTP 200), then passed after route removal.
- Full pytest suite: 214 passed, including RU/EN LibreOffice rendering regressions; one existing upstream Starlette deprecation warning.
- Frontend typecheck and production build passed using macOS dependencies with a package-lock identical to the source checkout.
- The actual ReportsDashboard rendered for RU, ENG with matches, ENG empty and loading; no CSV controls remain.
- The supplied 3.3 MB roadmap JSON produced successful plan/PPTX responses for RU and EN (30/29 slides); Title fallback remains.
- Independent read-only review of 3106e63..15919e5: no Critical, Important or Minor findings.
- Existing ENG empty text while reports load is preserved; removing CSV adds no new behavior there.
