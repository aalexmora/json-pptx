# Marketing Title Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Use Requirement.Title when the selected RU/EN marketing title is absent and display a nonblocking data error without losing the requirement.

**Architecture:** Resolve display text once in normalize_roadmap; keep language Visibility filters. Return missing-title diagnostics through existing quality_issues, preserving the blocking errors channel for invalid structures. Extend the existing quality dashboard with requirement IDs and language labels while keeping generation enabled.

**Tech Stack:** Python/FastAPI, React/TypeScript, python-pptx, existing local ARM64 image delivery.

**Spec:** The user's instruction in this chat overrides the former mandatory RU title and EN omission rules.

## Global Constraints

- Missing includes absent, null, blank or nonstring marketing titles; use a nonblank string Title.
- Existing marketing text and Visibility behavior stay intact; do not substitute the other language's marketing title.
- Errors identify the field, language, requirement and release for the selected visible language.
- If Title is also unavailable, retain the invalid-data handling: RU has no usable text and remains invalid; EN cannot render that requirement and reports the missing fallback.
- Do not change the user's JSON. Use synthetic regressions and the attached JSON only for local smoke checks.
- Keep layout/template contracts and user data intact; save locally and refresh the ready Mac image after checks.

## Review Focus

- Empty strings and whitespace must behave like null.
- EN fallback must include the requirement without admitting RU-only content.
- Nonblocking data errors must not populate errors or disable generation.
- Existing date diagnostics must remain readable and searchable.
- Both RU and EN PPTX text must contain Title, not the other marketing field.

### Task 1: Resolve titles and expose actionable data errors

**Files:** `roadmap_generator/schema.py`, `frontend/src/types.ts`, `frontend/src/App.tsx`, `tests/test_schema.py`, `tests/test_marketing_title_fallback.py`, `roadmap_generator/version.py`, `roadmap_generator/release_log.py`, `README.md`, `AGENTS.md`.

**Interfaces:** Existing validate_roadmap and normalize_roadmap signatures stay intact. QualityIssue adds optional requirement_id, requirement_title, language and field. Existing plan.errors stays empty for a usable Title fallback.

- [x] Write and observe failing schema/API/PPTX regressions; update obsolete EN omission expectations.
- [x] Implement selected-language fallback and error diagnostics; update the quality dashboard and policy documentation.
- [x] Run full pytest and frontend typecheck/build; smoke-test the provided JSON in RU and EN and inspect representative rendered slides. Result: 218 tests passed (one upstream Starlette warning); TypeScript/build and actual quality-component rendering passed. Original input generates RU30/EN29 slides with requirement11140787 retained and one missing-title error per selected language. Both affected slides were inspected after PDF conversion.
- [ ] Review, commit locally, rebuild/validate the ready ARM64 image and issue a fresh verified Mac command. Host runtime remains unverified until user execution.

Rollback: return to the previous local package/image; use the Mac launcher's existing cold backups if an installed image is updated.

Visual QA found the synthetic placeholder inherited 18 pt plus internal padding while packing estimates use 14 pt and slot width. Adding the fallback exposed clipping of following features. The service template is aligned to 14 pt with zero internal padding; uploaded templates and renderer styles are not changed. An opt-in LibreOffice/Poppler test proves all eight synthetic feature-end markers stay above the footer in RU and EN; both failed before the template adjustment. Real-input body bottoms are 485.67 pt (RU) and 435.25 pt (EN), above the 504 pt footnote area.
