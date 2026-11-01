# ContextKiln: Plan for the Agentic Layer and Open Models

**Goal:** Create a git repo at `~/develop/contextkiln` with two parts:

1. An **agentic layer** based on `tac-8/tac8_app1__agent_layer_primitives`: `specs/`, `.claude/commands/` and `adws/`. Each ADW can run on either Claude or a **local open model on this Mac**.
2. A minimal **application layer**: the ContextKiln shell. It has an LLM chat for tech and software engineering help, plus an "escalate to a human" path. You then build ContextKiln incrementally *through* the ADWs.

You also want to learn about open models along the way, so Phase 1 is an experiment track with its own notes.

---

## Current status and decisions (updated 2026-11-01)

**Phase 2 is complete. Phase 3 is next.** These decisions override anything later in this plan that assumes otherwise, including mentions of a public repo in Phases 5–7 and the risks section.

| Decision | Detail | What it means |
|---|---|---|
| **The repo is private** | [`philjohnson74/contextkiln`](https://github.com/philjohnson74/contextkiln). The copied TAC-8 code has no visible licence, and its origin may be private course material. | **Check the TAC-8 terms, or replace the copied code, before going public.** Keep following the public-repo hygiene rules so the repo stays ready for it. |
| **Licence is FSL-1.1-MIT** | Each version becomes available under MIT two years after release. The copyright holder is currently `philjohnson74`. | The licence only covers code we own, so it doesn't settle the TAC-8 question. |
| **`main` has no branch protection** | The current GitHub plan doesn't offer it for private repos. | GitHub won't block a push to `main` or a merge that skips checks, so ADW code has to enforce both. See Phases 3 and 5. |
| **Claude Code can't run `gh` or `git push` in this repo** | They're in the `deny` list in `.claude/settings.json`. This applies to interactive sessions as well as agents. | ADW Python code runs them directly, which the deny rules don't affect. Otherwise you run them yourself. |

---

## Starting point (checked on 2026-10-17)

| Item | State | Implication |
|---|---|---|
| Machine | Mac Studio, **Apple M5 Max, 36 GB unified memory**, ~306 GB free disk | Practical local models are ~20–32B, ideally MoE, at 4-bit. Larger dense models won't fit with a usable context window. |
| macOS | 27.0.1 | — |
| Installed | git, gh, node, brew, system python3 | — |
| **Missing** | `uv`, `claude` (Claude Code CLI), `ollama` / LM Studio / MLX | Installed in Phase 0 / Phase 1. |
| Reference | `~/develop/tac-8/tac8_app1__agent_layer_primitives` | We copy and adapt `adws/adw_modules/agent.py`, `adw_prompt.py`, `adw_slash_command.py`, `adw_chore_implement.py` and the `chore` / `feature` / `implement` / `prime` / `start` commands. |

**What has to change in the TAC-8 primitives for open models:** `agent.py` hard-codes `model: Literal["sonnet", "opus"]`. Its `get_safe_subprocess_env()` also passes only `ANTHROPIC_API_KEY` through to the `claude` subprocess. To run on a local model, Claude Code needs `ANTHROPIC_BASE_URL` (and an auth token) pointing at a local server that speaks the Anthropic Messages API. It also needs an arbitrary model name. So we add **model profiles** (Phase 3).

---

## Phase 0: Machine prerequisites (~30 min)

```bash
brew install uv
```
```bash
npm install -g @anthropic-ai/claude-code
```
```bash
gh auth status
```

- If `gh auth status` shows you're not logged in, run `gh auth login`. ADWs push branches and open PRs as you, so `gh` needs the `repo` scope.
- Run `claude` once interactively and sign in. Use your subscription for interactive work, and an `ANTHROPIC_API_KEY` for headless ADW runs.
- `git config --global user.name/user.email` if not already set.
- Smoke test the existing primitives before copying anything: `cd tac-8/tac8_app1__agent_layer_primitives && ./adws/adw_prompt.py "list the files in apps/"`. This proves uv + claude + the agent module work end to end.

**Done when:** `adw_prompt.py` runs and writes JSONL output under `agents/`.

---

## Phase 1: Open models on the Mac (experiment track, ~1–2 sessions)

Write notes as you go into `contextkiln/ai_docs/local_models.md`. The notes are a learning record, and agents can read them later.

### 1a. Learn the runtimes (pick one primary, try one more)

| Runtime | Why | Notes |
|---|---|---|
| **Ollama** (primary) | Simplest. Recent versions expose an **Anthropic-compatible `/v1/messages` endpoint**, so Claude Code can talk to it directly. They also expose an OpenAI-compatible `/v1` that the ContextKiln app can use. | `brew install ollama`, `ollama serve`. Check `ollama --version` and the Ollama docs for "Claude Code" to confirm Anthropic compatibility in your version. |
| **LM Studio** (MLX engine) | GUI and model browser. **MLX** is Apple's native framework and is often faster than GGUF/llama.cpp on Apple Silicon. Also serves OpenAI- (and in newer builds Anthropic-) compatible APIs. | Good for comparing GGUF and MLX speed on the same model. |
| `mlx-lm` / `llama.cpp` (optional) | Bare-metal understanding: quantization, context, KV cache. | `uv tool install mlx-lm`, then `mlx_lm.server`. |
| **LiteLLM proxy** (fallback) | Translates Anthropic API ⇄ any backend if a runtime lacks Anthropic compatibility. Also gives you a single endpoint for routing and logging. | `uvx litellm --config litellm.yaml` |

### 1b. Understand the memory budget (key learning for 36 GB)

- By default macOS lets the GPU use roughly 70–75% of unified memory (~26–27 GB here). The rest stays with the OS, Claude Code, your editor and the browser.
- Memory needed ≈ **model weights** (params × bits ÷ 8) **+ KV cache** (grows linearly with context length) + overhead.
- Claude Code's system prompt and tool definitions alone are ~15–20k tokens. **Agentic coding needs ≥32k context, ideally 64k.** Ollama's default context is small, so set `OLLAMA_CONTEXT_LENGTH=65536` (or larger), or the agent will silently lose its instructions.
- Worked example: a 30B-A3B MoE model at Q4 is ~18 GB of weights. With a 64k context it needs about +6 GB of fp16 KV cache, so ~24–25 GB total. That fits, but only just. With `OLLAMA_FLASH_ATTENTION=1` + `OLLAMA_KV_CACHE_TYPE=q8_0`, the KV cache is roughly halved.
- You *can* raise the GPU wired-memory limit (`sudo sysctl iogpu.wired_limit_mb=...`). Treat that as an informed, reversible experiment: it resets on reboot. Only use it once you understand the trade-off.

### 1c. Candidate models to evaluate

Pick 2–3 that support **tool calling** (required for agentic use). Check the Ollama library and LM Studio for current versions, because this landscape moves monthly.

- **Qwen3-Coder 30B-A3B** (MoE, ~3B active, so fast). The strongest default for coding agents at this memory size.
- **GPT-OSS 20B** (MoE, ~13 GB). Good tool use and reasoning, and leaves lots of headroom for context.
- **Devstral Small (24B)**. Mistral's model trained specifically for agentic software engineering.
- A small, fast model (e.g. a 4–8B Qwen) to drive the **ContextKiln chatbot** itself during development. The app's model doesn't need to be your coding model.

### 1d. Experiments (each one is a short note in `ai_docs/local_models.md`)

1. **Raw throughput:** `ollama run <model> --verbose` → record prompt-processing tok/s and generation tok/s. On Apple Silicon, prompt processing of large agent contexts is usually the bottleneck, not generation.
2. **Claude Code on a local model, interactively:**
   ```bash
   ANTHROPIC_BASE_URL=http://localhost:11434 ANTHROPIC_AUTH_TOKEN=ollama ANTHROPIC_API_KEY="" claude --model qwen3-coder:30b
   ```
   Ask it to read and edit a file in a throwaway repo. Watch for broken tool calls and lost instructions.
3. **Headless:** the same command with `-p "..." --output-format stream-json --verbose`. This is exactly how the ADWs call it.
4. **Bake-off:** run the *same* small chore through `adw_chore_implement.py` with each model *and* with Sonnet (Phase 3 makes this a one-flag change). Record wall time, whether the spec followed the template, and whether the result works.

**Done when:** you have one local model that can complete a `/chore` → `/implement` cycle on a trivial task, and you have notes explaining why the others did or didn't.

---

## Phase 2: Scaffold the ContextKiln repo (~1 session)

**Done on 2026-11-01, with changes.** The repo was created as private rather than public, FSL-1.1-MIT was chosen, and step 7 wasn't possible on the current GitHub plan. The steps below are the original plan. The tree shows the intended end state: `models.py`, `git_ops.py`, `github.py` and the remaining commands arrive in Phases 3 and 5, and the apps in Phase 4.

```
contextkiln/
├── README.md                 # what ContextKiln is + how the agentic layer works
├── CLAUDE.md                 # conventions agents must follow (stack, commands, test cmd)
├── PLAN.md                   # this file
├── .env.sample               # ANTHROPIC_API_KEY, model profile vars, app LLM vars
├── .gitignore                # .env, agents/, trees/, __pycache__, node_modules, *.db
├── .github/workflows/        # ci.yml, claude-review.yml (Phase 5)
├── .claude/
│   ├── commands/             # chore, feature, bug, implement, prime, start, test,
│   │                         # commit, pull_request, review_pr, address_review, fix_ci
│   └── settings.json         # permissions allowlist for headless runs
├── adws/
│   ├── adw_modules/
│   │   ├── agent.py          # adapted from TAC-8 (model profiles)
│   │   ├── models.py         # NEW: profile → env + model name
│   │   ├── git_ops.py        # NEW: sync main, branch, commit, push
│   │   └── github.py         # NEW: gh wrapper (issues, PRs, comments)
│   ├── adw_prompt.py
│   ├── adw_slash_command.py
│   ├── adw_chore_implement.py
│   └── adw_feature_implement.py   # NEW: /feature → /implement
├── specs/                    # plans written by agents
├── ai_docs/                  # local_models.md, third-party API notes for agents
├── app_docs/                 # feature docs written after each ADW
├── agents/                   # ADW output (gitignored)
└── apps/
    ├── backend/              # FastAPI (Python, uv)
    └── frontend/             # Vite + React + TS
```

Steps:
1. `git init` and copy in the TAC-8 primitives listed above.
2. Rewrite each command's **Codebase Structure** section (in `chore.md`, `feature.md`, `prime.md`) for ContextKiln. These sections are the context the agents rely on most.
3. Add `bug.md` and `test.md` commands (TAC-8's scaled layer), with the real test commands (`uv run pytest`, `npm test`).
4. Write `CLAUDE.md`: stack, run commands, test commands, and "always update `app_docs/` after a feature".
5. **Prepare for a public repo** before the first commit:
   - `.gitignore` covers `.env`, `agents/`, `trees/`, `*.db`, and any model or cache files.
   - Add a `LICENSE`. MIT is simplest. If you want to keep commercial control of ContextKiln while still showing the code, consider a source-available licence such as BSL or FSL. Decide this now; it's awkward to change later.
   - Make sure `.env.sample` contains placeholders only. Grep the tree for keys before the first push.
6. **First commit and publish:**
   ```bash
   gh repo create contextkiln --public --source . --push --description "AI tech consultancy app, built through agentic developer workflows"
   ```
7. **Protect `main`:** in the GitHub repo settings, require a PR before merging and block force-pushes. Agents then can't push to `main` directly; every change arrives as a PR that you review and merge.

---

## Phase 3: Make the agentic layer model-pluggable (~1 session)

This is the bridge between the TAC-8 layer and the open-model experiments.

- **`adw_modules/models.py`** defines named profiles:
  ```python
  PROFILES = {
      "claude":      {"model": "sonnet"},                               # uses ANTHROPIC_API_KEY
      "claude-opus": {"model": "opus"},
      "local":       {"model": os.getenv("LOCAL_MODEL", "qwen3-coder:30b"),
                      "env": {"ANTHROPIC_BASE_URL": "http://localhost:11434",
                              "ANTHROPIC_AUTH_TOKEN": "ollama", "ANTHROPIC_API_KEY": ""}},
  }
  ```
- **`agent.py`**: change `model: Literal[...]` to `model: str`. Add `profile: str`. Merge the profile's env into `get_safe_subprocess_env()`, and pass `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` through.
- Every ADW gets `--profile local|claude|claude-opus` (default from `ADW_PROFILE` in `.env`).
- **Per-step profiles** in composed ADWs: e.g. `--plan-profile claude --build-profile local`. A strong model writes the spec and a local model implements it. This is the most interesting cost/quality experiment.
- **Run log:** append one line per agent run to `agents/runs.jsonl` with {adw_id, step, profile, model, duration_ms, num_turns, success}. Read it from the stream-json result message. This is the data source for comparing models, and later for **pricing ContextKiln's own agentic support**.
- **`adw_health_check.py`**: checks that `claude`, `uv` and the local server are reachable, that the model is pulled, and that the context length is large enough. Run it before any workflow.

### Git + GitHub lifecycle for every ADW

Every ADW runs through the same deterministic wrapper in Python code, not in prompts, so even a weak local model can't get it wrong.

**`git_ops.py` must refuse to commit or push when the current branch is `main`, and abort the ADW if it is.** With no branch protection, this check is what keeps ADWs off `main`.


1. **Sync:** check the working tree is clean (abort if not), then `git fetch origin && git checkout main && git pull --ff-only`.
2. **Branch:** `git checkout -b adw/{type}-{adw_id}-{slug}`, e.g. `adw/chore-a1b2c3d4-health-endpoint`.
3. **Plan → build:** run the slash commands (`/chore` or `/feature`, then `/implement`).
4. **Verify:** run `scripts/test.sh`. If it fails, still open the PR, but **as a draft**, with the failure output in the body.
5. **Commit:** a `/commit` command writes a conventional message (`feat: …`, `chore: …`) with an `adw_id` trailer. Python then runs the actual `git add`/`git commit`, so nothing outside the repo is staged.
6. **Push + PR:** `git push -u origin <branch>`, then `gh pr create` via a `/pull_request` command for the title and body. The body includes a link to the spec in `specs/`, a summary of changes, the test result, and the profile/model/turns/duration from `runs.jsonl`. If the ADW was started from an issue, the body includes `Closes #N`.
7. **Return to `main`** so the next ADW starts clean.

**For now, you merge.** Until Phase 5 adds automated Claude review, your review on GitHub is the quality gate. That matters especially for local-model output.

- `--issue N` option: fetch the issue title and body with `gh issue view N --json` and use them as the prompt. The ADW comments on the issue with the `adw_id`, then with the PR link.
- `--no-pr` option: for local experiments and bake-offs that shouldn't touch GitHub.
- Before this works, add `/commit` and `/pull_request` commands, both adapted from the TAC-8 scaled layer.

**Done when:** `./adws/adw_chore_implement.py "add a /health endpoint" --profile local` and `--profile claude` each:
- pull the latest `main`,
- produce a spec in `specs/` and working code on their own branch,
- open a PR on GitHub,
- and appear in `runs.jsonl`.

---

## Phase 4: ContextKiln MVP shell (the application layer)

Keep this deliberately thin. It's the canvas the ADWs paint on. **Build only the skeleton by hand (or with interactive Claude Code); everything after that goes through ADWs.**

**Backend: FastAPI + SQLite**
- `GET /health`
- `POST /api/chat` takes `{conversation_id?, message}` and streams a reply from an **LLM provider interface**:
  - `LLMProvider` protocol with `OpenAICompatibleProvider` (hits Ollama's `/v1` locally, so it's free in dev) and later `AnthropicProvider`.
  - Choose the provider with env vars: `CK_LLM_PROVIDER`, `CK_LLM_MODEL`, `CK_LLM_BASE_URL`.
  - System prompt: "ContextKiln tech consultant". Scope it to software and infrastructure questions, and tell it to recommend human escalation when out of its depth.
- `POST /api/escalations` creates a human-support request (conversation link, summary, status `open`). There is no payment and no auth yet, and there is no human dashboard yet; the request is just a row in the database.
- Tables: `conversations`, `messages`, `escalations`.
- pytest tests for each endpoint, with the LLM provider faked.

**Frontend: Vite + React + TS**
- A single chat page: message list, input, streaming reply, and a "Talk to a human" button that calls `/api/escalations`.

**Scripts:** `scripts/start.sh`, `scripts/test.sh`, `scripts/stop.sh`. The `/start` and `/test` commands, and later the test ADW, rely on these.

**Done when:** you can chat with a local model in the browser, click escalate, and see the row in SQLite. `scripts/test.sh` is green.

---

## Phase 5: Automated Claude PR review + the ship loop (~1–2 sessions)

The aim is a closed loop. An ADW opens a PR, Claude reviews it on GitHub, and the ADW fixes what the review raised and pushes again. This repeats until the PR is approved and tests pass, then the PR is merged.

```
ADW (Mac)                                   GitHub
──────────                                  ──────
plan → build → test → push → open PR  ──▶   CI workflow (tests)
                                            Claude review workflow ──▶ inline comments + verdict check
adw_ship.py waits for checks          ◀──
  ├─ CI red          → /fix_ci agent → push ──▶ (re-runs)
  ├─ changes needed  → /address_review agent → push ──▶ (re-review)
  ├─ main moved      → merge main, resolve, re-test → push
  ├─ approved + green → merge, close issue, back to main
  └─ round limit hit → label needs-human, notify you
```

### 5a. GitHub side: CI and Claude review

1. **CI workflow** (`.github/workflows/ci.yml`): runs on `pull_request`. It installs uv + node and runs `scripts/test.sh`. Name the job `ci`; it becomes a required check.
2. **Claude review workflow** (`.github/workflows/claude-review.yml`): uses Anthropic's official **`anthropics/claude-code-action`**.
   - Setup: in an interactive `claude` session inside the repo, run `/install-github-app`. It installs the Claude GitHub App and adds the API key as a repo secret. Alternatively, add `ANTHROPIC_API_KEY` under repo **Settings → Secrets → Actions** yourself.
   - Triggers: `pull_request: [opened, synchronize, ready_for_review]`. Skip draft PRs.
   - Pin the action version. Check its README for the current inputs (prompt, `claude_args` such as `--model` and `--max-turns`, allowed tools), because they evolve.
3. **Review prompt is versioned in the repo** (`.claude/commands/review_pr.md`), like every other prompt. Improving the reviewer then goes through a PR like any other change. The reviewer:
   - reads the spec in `specs/` that the PR links to, plus `CLAUDE.md`;
   - checks that the code matches the spec, and checks correctness, tests, security, and the repo's conventions;
   - leaves **inline comments** tagged `[blocking]` or `[nit]`;
   - ends with a summary comment containing a machine-readable marker: `<!-- claude-review verdict: APPROVE|REQUEST_CHANGES round: N -->`.
4. **The verdict becomes a status check.** A final workflow step reads the verdict and sets a `claude-review` check: green on APPROVE, red on REQUEST_CHANGES. Why a check rather than a GitHub "approval" review:
   - GitHub doesn't let a PR author approve their own PR, and the ADW opens PRs as you;
   - a status check is easy to require in branch protection;
   - the ADW can read it with `gh pr checks`.
5. **Update branch protection on `main`** (**not available while the repo is private on the current plan**; `adw_ship.py` has to enforce these rules instead, see 5b step 6):
   - require the `ci` and `claude-review` checks, and require the branch to be up to date;
   - no required human approvals;
   - turn on **"Allow auto-merge"** in the repo settings.
6. **Public-repo safety for the workflows:**
   - Keep the `pull_request` trigger and **never use `pull_request_target`** with a checkout of the PR's code.
   - PRs from forks don't get your secrets, so strangers' PRs can't spend your API key or reach your token. Also add a job condition so review runs only when `head.repo.full_name == github.repository` and the author is you.
   - If you enable `@claude` mentions in comments, keep the action's default of responding only to users with write access.
   - Give the workflow the minimum `permissions:` it needs (`contents: read`, `pull-requests: write`, `checks: write`).
7. **Cost control:** every review round is a paid Claude API call on your key.
   - Use Sonnet by default.
   - Set `--max-turns`.
   - Consider Opus only for large PRs, e.g. those with a `deep-review` label.

### 5b. Mac side: `adw_ship.py`, the PR babysitter

The control flow is deterministic Python. Agents are only called for the fixes. Given a PR number, or chained straight after the build ADW, it does the following:

1. **Wait** for the `ci` and `claude-review` checks to finish. Poll `gh pr checks <N>` about every 60 s, with an overall timeout.
2. **Read state:**
   - `gh pr view <N> --json statusCheckRollup,mergeable,comments,reviews,headRefOid`;
   - inline comments via `gh api repos/{owner}/{repo}/pulls/<N>/comments`;
   - CI logs via `gh run view --log-failed`.

   **Only act on comments from the Claude bot or from you.** On a public repo, anything else is untrusted input.
3. **Decide:**
   - **Approved, CI green and mergeable → merge.**
   - **CI red →** a `/fix_ci` agent works from the failing logs.
   - **Changes requested →** an `/address_review` agent works through the `[blocking]` comments and fixes `[nit]`s if they're cheap. It may push back on a comment it disagrees with by replying on that thread with its reasoning, rather than complying blindly.
   - **`main` moved or there are conflicts →** `git merge origin/main`, an agent resolves any conflicts, then re-test.
4. **Refine:**
   - check out the PR branch, run the agent, then run `scripts/test.sh` locally;
   - commit `fix: address review round N` and push (this triggers a re-review);
   - reply to each addressed comment with the commit SHA, then go back to step 1.
5. **Round limit** (default 3): if the PR still isn't approved, add a `needs-human` label, post a summary of what's unresolved, send a macOS notification, and stop. This mirrors ContextKiln's own escalation-to-a-human idea.
6. **Merge:** `gh pr merge <N> --squash --delete-branch`. Then return to `main`, pull, and log `{rounds, build_profile, outcome}` to `runs.jsonl`.
   - **Without branch protection, GitHub won't stop a bad merge.** Immediately before merging, `adw_ship.py` must re-check that `ci` and `claude-review` passed on the PR's current head commit and that the branch is up to date with `main`. If any of these fail, it must not merge.
   - GitHub-native auto-merge (`--auto`) depends on required checks, so don't use it unless branch protection becomes available.

### 5c. Composed workflow and a trust ramp

- **`adw_sdlc.py "prompt" | --issue N`** runs plan → build → test → PR → ship end to end. Run without arguments, it picks up the next issue in the backlog.
- **The key experiment:** the builder can be a **local model** while the reviewer is always **Claude on GitHub**. Track **rounds-to-approval per build profile** in `runs.jsonl`. That gives a real measure of how good each local model is.
- **Ramp up the trust** with a `--merge` option:
  1. `--merge=never`: babysit until approved, then you merge. Compare your judgement with Claude's for a few weeks.
  2. `--merge=label`: auto-merge only PRs labelled `auto-merge`, e.g. chores and docs.
  3. `--merge=auto`: the default. You spot-check merged PRs and still get the `needs-human` escalations.

**Done when:** GitHub issue → `adw_sdlc.py --issue N` → PR → at least one real review round with a fix → approved → merged → issue closed, all without you touching it.

---

## Phase 6: Build ContextKiln through ADWs (ongoing)

From here, **every change starts as an ADW and ends as a reviewed, merged PR.** Keep the backlog as **GitHub issues**: `./adws/adw_sdlc.py --issue 7` picks one up and ships it, and the PR closes the issue on merge. The public issue + PR history then doubles as a showcase of the agentic workflow.

Suggested first issues (each one is a good bake-off between local and Claude profiles):

1. Conversation history sidebar (list and resume conversations).
2. Markdown + code-block rendering in chat replies.
3. LLM-generated escalation summary ("summarise this conversation for a human engineer").
4. Escalation triage: the bot classifies "can I handle this?" and offers escalation proactively.
5. Simple admin page that lists and updates escalations (the human-consultant side).
6. Usage metering per conversation (tokens in and out). This is the foundation for future pricing.
7. User accounts/auth (later; a good candidate for Claude Opus planning).
8. Pricing tiers: free agentic tier, paid agentic usage, a premium for human escalation, and Stripe test mode (much later).

---

## Phase 7: Grow toward the scaled agentic layer (as needed)

Bring these in from the TAC-8 scaled layout only when the pain is real:

- `state.py` + `agents/{adw_id}/adw_state.json`: chain plan → build → test → review across separate processes.
- `worktree_ops.py` + `trees/`: one worktree per ADW, so several ADWs can run in parallel without fighting over one checkout. Parallelism is limited by 36 GB RAM: realistically one local model at a time, or mix local and Claude.
- `adw_triggers/trigger_cron.py`: pick up GitHub issues automatically. **Because the repo is public, anyone can open an issue, and issue text goes straight into an agent's prompt.** So trigger only when *you* apply an `adw` label, or when the issue author is you (check `author.login`). Never trigger on arbitrary issues or comments.
- **Webhook trigger** (`adw_triggers/trigger_webhook.py`) to replace polling in `adw_ship.py`. GitHub would send review and check events to your Mac through a tunnel such as cloudflared. Only worth it once polling feels slow.
- **Run ADWs in GitHub Actions too:** for Claude-profile builds, the whole SDLC can run in the cloud without your Mac. Local-model builds must stay on the Mac.
- `.claude/hooks/`: guardrails, e.g. block `rm -rf` and writes outside the repo. These matter more with weaker local models.

---

## Risks and things to watch

- **Local models + Claude Code:** Claude Code's prompts are tuned for Claude. Expect more malformed tool calls, looping and ignored instructions from open models. Mitigations: large context, a tool-calling-capable model, tighter specs, and the plan-with-Claude/build-local split.
- **Silent context truncation** is the #1 cause of "the local model is dumb". Always verify the context length.
- **Speed:** prompt processing of a 20k+ token agent context can take tens of seconds per turn locally. Use the run log rather than guessing.
- **`--dangerously-skip-permissions`** in headless ADWs: use it only inside the repo and later in worktrees, and add hooks before enabling auto-triggers.
- **Public repo hygiene:**
  - Secrets live only in `.env`. Consider enabling GitHub secret scanning and push protection (free for public repos).
  - Run logs in `agents/` can contain prompts and file contents, so they stay gitignored. Only the summary line goes into PR bodies.
  - Agents should never push to `main`. While there's no branch protection, the `git push` deny rule and the `git_ops.py` check enforce this.
- **Review loop failure modes:**
  - *Ping-pong*: the fixer and reviewer disagree forever. The round limit and the `needs-human` escalation handle this.
  - *Reviewer drift*: the reviewer gets stricter or looser over time. Its prompt is versioned, so tune it through PRs.
  - *Same-model leniency*: when Claude builds and Claude reviews, consider an Opus reviewer for Sonnet builds.
  - *Auto-merging broken code*: required CI checks and the trust ramp are the guards.
- **Cost tracking:** `total_cost_usd` in Claude Code output is meaningless for local runs. Log turns and duration instead, and token counts if available.

## Suggested order of sessions

| # | Session | Phases |
|---|---|---|
| 1 | Prereqs + Ollama + first local model talking to Claude Code | 0, 1a–1b, 1d.1–2 |
| 2 | Model bake-off on the TAC-8 primitives repo | 1c–1d |
| 3 | Scaffold repo, publish publicly on GitHub, model profiles + git/PR lifecycle | 2, 3 |
| 4 | ContextKiln shell | 4 |
| 5 | CI + Claude review workflows, `adw_ship.py`, `adw_sdlc.py` (start with `--merge=never`) | 5 |
| 6+ | Backlog via ADWs, adding scaled-layer pieces when needed | 6, 7 |
