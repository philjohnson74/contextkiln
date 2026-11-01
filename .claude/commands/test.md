# Application Validation Test Suite

Run the validation tests for the backend and frontend, and return the results as JSON for automated processing.

## Instructions

- Run each test in the sequence below, from the project root.
- Time out each command after 5 minutes.
- If a command returns a non-zero exit code, mark it as failed, capture the error output, and stop running tests.
- If a test's manifest file doesn't exist, the application isn't built yet: mark that test as skipped and continue.
- Don't fix anything. Only report.
- IMPORTANT: Return ONLY the JSON array, with no other text or markdown formatting. It will be passed straight to a JSON parser.

## Test Execution Sequence

1. **Backend tests**
   - Manifest: `apps/backend/pyproject.toml`
   - Command: `cd apps/backend && uv run pytest`
   - test_name: "backend_tests"

2. **Frontend tests**
   - Manifest: `apps/frontend/package.json`
   - Command: `cd apps/frontend && npm test`
   - test_name: "frontend_tests"

## Report

Sort failed tests to the top. Omit `error` when a test didn't fail.

```json
[
  {
    "test_name": "string",
    "status": "passed | failed | skipped",
    "execution_command": "string",
    "error": "optional string"
  }
]
```
