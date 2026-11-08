# CI

A GitHub Actions workflow in `.github/workflows/ci.yml` runs the full test suite.

## Triggers

- Every `pull_request`, on any branch.
- Every push to `main`.

It never uses `pull_request_target`.

## The `ci` job

- Runs on `ubuntu-latest` with a 20-minute timeout.
- Token permissions are `contents: read` only.
- Concurrency group is per ref (`ci-<ref>`). A newer run cancels one still in progress.
- Needs no secrets. Tests fake the LLM provider.

Steps: checkout, set up uv (cache keyed on `apps/backend/uv.lock`), install Python 3.12, set up Node 22 (npm cache keyed on `apps/frontend/package-lock.json`), then `./scripts/test.sh`.

## What it runs

`./scripts/test.sh` runs the ADW tests, the backend pytest suite and the frontend tests.

## Reproduce locally

```bash
./scripts/test.sh
```
