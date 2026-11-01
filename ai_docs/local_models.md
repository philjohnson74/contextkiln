# Local Models on the Mac Studio

Learning log for running open models locally. Agents read this file too, so keep facts accurate and dated.

## Machine

- Mac Studio, Apple M5 Max, 36 GB unified memory. **28.1 GiB of it is available to the GPU (Metal)**, and every model + context must fit in that.
- Runtime: Ollama 0.40.6 (Homebrew formula, `brew install ollama`). The server is started manually with `ollama serve` so its settings and logs are visible.
- Both models below run on Ollama's **llama.cpp engine** (`RUNNER llamacpp` in `ollama ps`), using GGUF model files.

## Server settings

| Variable | Value | Why |
|---|---|---|
| `OLLAMA_CONTEXT_LENGTH` | 65536 | Claude Code's system prompt and tools are ~20k tokens per turn. Ollama's default here would be 32768. |
| `OLLAMA_FLASH_ATTENTION` | 1 | Faster attention, and required for a quantized KV cache. |
| `OLLAMA_KV_CACHE_TYPE` | q8_0 | Roughly halves KV cache memory compared with f16. |

---

## Command cheat sheet

### Server

| What | Command | Notes |
|---|---|---|
| Start the server (own terminal tab, leave running) | `OLLAMA_CONTEXT_LENGTH=65536 OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 ollama serve` | Logs every request, model load and memory breakdown. |
| Check the server is up | `curl http://localhost:11434/api/version` | Returns `{"version":"0.40.6"}`. |
| Stop the server | **Ctrl+C** in the server tab | Unloads all models and closes port 11434. |

### Models on disk

| What | Command | Notes |
|---|---|---|
| Download a model | `ollama pull qwen3-coder:30b` | Stored in `~/.ollama/models`. Find tags at ollama.com/library. |
| List downloaded models | `ollama list` | Size on disk only. |
| Model details | `ollama show qwen3-coder:30b` | Architecture, parameters, context length, quantization, **capabilities** (`tools` is required for agentic coding), and default sampling parameters. |
| Delete a model | `ollama rm qwen3:4b` | Frees disk space. |

### Running and stopping

| What | Command | Notes |
|---|---|---|
| Chat interactively with speed stats | `ollama run qwen3-coder:30b --verbose` | Loads the model if it isn't loaded already. |
| Stop a reply mid-generation | **Ctrl+C** in the chat | Returns you to the `>>>` prompt. |
| Leave the chat | `/bye` or **Ctrl+D** | The model **stays loaded** for 5 minutes (keep-alive). |
| What's loaded in memory right now | `ollama ps` | SIZE = weights + KV cache + compute. You want `PROCESSOR 100% GPU`. Shows only the column headers when nothing is loaded. |
| Unload a model now | `ollama stop qwen3-coder:30b` | Prints nothing on success. Do this before loading a different large model. |

### Calling the API

OpenAI-compatible. ContextKiln's chatbot will use this:

```bash
curl -s http://localhost:11434/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"qwen3-coder:30b","messages":[{"role":"user","content":"Say hello in five words"}]}'
```

Anthropic-compatible. Claude Code and the ADWs will use this:

```bash
curl -s http://localhost:11434/v1/messages -H "Content-Type: application/json" -H "x-api-key: ollama" -H "anthropic-version: 2023-06-01" -d '{"model":"qwen3-coder:30b","max_tokens":100,"messages":[{"role":"user","content":"Say hello in five words"}]}'
```

Both endpoints were verified working on 2026-10-19.

### Claude Code on a local model (Phase 1d.2)

Launch command (the Ollama server must already be running):

```bash
ANTHROPIC_BASE_URL=http://localhost:11434 ANTHROPIC_AUTH_TOKEN=ollama ANTHROPIC_API_KEY="" CLAUDE_CODE_MAX_CONTEXT_TOKENS=65536 claude --model qwen3-coder:30b
```

What each variable does:

| Variable | Value | Purpose |
|---|---|---|
| `ANTHROPIC_BASE_URL` | `http://localhost:11434` | Sends Claude Code's API requests to Ollama instead of Anthropic. Ollama serves the Anthropic-compatible `/v1/messages`. |
| `ANTHROPIC_AUTH_TOKEN` | `ollama` | Any non-empty value. Ollama doesn't check it, but Claude Code needs a token to send. |
| `ANTHROPIC_API_KEY` | `""` | Blanks any real Anthropic key in the shell, so it isn't used or sent. |
| `CLAUDE_CODE_MAX_CONTEXT_TOKENS` | `65536` | Tells Claude Code the real context window. **Must match `OLLAMA_CONTEXT_LENGTH`.** |
| `--model` | `qwen3-coder:30b` | The Ollama model tag, passed through as the model name. |

**The "isn't recognized" warning (2026-10-19).** Without `CLAUDE_CODE_MAX_CONTEXT_TOKENS`, Claude Code shows:

```
⚠ Model "qwen3-coder:30b" isn't recognized · context assumed to be 200k tokens
```

- **Why it happens:** Claude Code knows the context window of every Claude model, but not of other models. For an unknown name it assumes 200k and only auto-compacts (summarises older history) near 200k.
- **Why it matters:**
  - The Ollama server only provides 65,536 tokens, and llama.cpp runs with `--context-shift`.
  - Past 65,536 tokens it **silently drops the oldest tokens** (Claude Code's system prompt and tool instructions) instead of returning an error.
  - So Claude Code would never learn it needs to compact, and the model would quietly lose its instructions.
- **The fix:** set `CLAUDE_CODE_MAX_CONTEXT_TOKENS=65536`. According to the Claude Code model configuration docs (code.claude.com/docs/en/model-config), it works on its own for model names that don't start with `claude-`. Claude Code then auto-compacts before the real limit.
- **Things that don't work here:**
  - `/autocompact` and `--autocompact` only accept 100k–1M tokens.
  - `CLAUDE_CODE_AUTO_COMPACT_WINDOW` is capped at the window Claude Code thinks the model has.
  - `CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1` only compacts after the server returns a too-long error, which llama.cpp's context shift never does.
- **If you change the context:** keep both numbers in step. E.g. with `OLLAMA_CONTEXT_LENGTH=98304`, set `CLAUDE_CODE_MAX_CONTEXT_TOKENS=98304`.

**Other things on the startup screen:**
- The banner says **"API Usage Billing"** because Claude Code is authenticating with a token rather than your subscription login. The requests go to localhost, so **nothing is billed**.
- To confirm requests really are local, send a message and watch the Ollama server tab: each turn appears as `POST "/v1/messages"`. If nothing shows up, the base URL isn't set in that shell.
- An `ollama run qwen3-coder:30b` chat open at the same time shares the same loaded model, so it costs no extra memory.

**Exiting:** `/exit`, or press Ctrl+C twice. The model stays loaded in Ollama for the 5-minute keep-alive.

**First things to try:**
1. `read README.md and summarise it`: tests the file-reading tool.
2. `create hello.py that prints today's date, then run it`: tests the write and Bash tools.
3. Watch for:
   - malformed tool calls;
   - loops;
   - ignored instructions;
   - time per turn: the first turn is the slowest, because the ~20k-token system prompt has to be processed before the prompt cache helps.

**Optional shortcut:** add this to `~/.zshrc`, then run `claude-local` in any directory:

```bash
alias claude-local='ANTHROPIC_BASE_URL=http://localhost:11434 ANTHROPIC_AUTH_TOKEN=ollama ANTHROPIC_API_KEY="" CLAUDE_CODE_MAX_CONTEXT_TOKENS=65536 claude --model qwen3-coder:30b'
```

### Reading the `--verbose` stats

- **`prompt eval rate`** is how fast the model *reads* input (tokens/s). It's the bottleneck for agentic coding, because each turn re-reads ~20k tokens. Only measure it with a **large** prompt: tiny prompts (10–50 tokens) show misleadingly low rates, because fixed overhead dominates.
- **`eval rate`** is how fast the model *writes* output (tokens/s).

---

## Models tried

### Summary

| Date | Model | Disk | Loaded (GPU) | Context | Tools | Prompt eval tok/s | Gen tok/s | Load time |
|---|---|---|---|---|---|---|---|---|
| 2026-10-18 | `qwen3:4b` | 2.5 GB | ~7.9 GiB | 65536 | yes + thinking | n/a (only tiny prompts measured) | **~106** | 1.0 s |
| 2026-10-19 | `qwen3-coder:30b` | 18 GB | ~20.6 GiB (`ollama ps`: 22 GB) | 65536 | yes | **~2,250** (719-token prompt) | **~95–99** | 4.8 s cold, 1.5 s warm |

### `qwen3:4b`: Qwen3 4B Thinking 2507

- **What it is:** a small dense model, and the *Thinking* variant, so it writes out its reasoning before answering. Good for learning the tools, and a candidate for the ContextKiln chatbot in development. Not intended as a coding agent.
- **Architecture:** `qwen3`, 4.02B parameters, 36 layers, 32 query heads / **8 KV heads** (grouped-query attention, 4:1). Trained context 262,144 tokens.
- **Quantization:** Q4_K_M, 4.95 bits per weight. Most tensors are q4_K, and 37 more sensitive ones are kept at q6_K.
- **Memory at 64k context:**

  | Part | Size |
  |---|---|
  | Weights | 2,375 MiB |
  | **KV cache** | **4,896 MiB** |
  | Compute | 673 MiB |
  | **Total** | **7,945 MiB** |

  The KV cache is twice the size of the weights.
- **GPU:** 37/37 layers offloaded (100% GPU).
- **Speed:** generated 2,301 tokens at **106 tok/s**. Most of those were thinking tokens, so an answer takes ~22 s even though output is fast.
- **Default sampling:** temperature 0.6, top_p 0.95, top_k 20.
- **Licence:** Apache 2.0.

### `qwen3-coder:30b`: Qwen3 Coder 30B A3B Instruct

- **What it is:** a **mixture-of-experts** (MoE) coding model. It has 128 experts, of which **8 are active per token**. That's 30.5B parameters in total but only ~3.3B used per token ("A3B"), which is why it generates as fast as the 4B model despite being 7× larger. It's not a thinking model, so it answers directly. This is the primary candidate for local agentic coding.
- **Architecture:** `qwen3moe`, 48 layers, **4 KV heads**. Trained context 262,144 tokens.
- **Quantization:** Q4_K_M, 4.86 bits per weight, 17.28 GiB.
- **Memory at 64k context:**

  | Part | Size |
  |---|---|
  | Weights | 17,524 MiB |
  | KV cache | **3,264 MiB** |
  | Compute | 268 MiB |
  | **Total** | **21,057 MiB** |

  This leaves ~7.5 GiB of GPU headroom. Note that the KV cache is *smaller* than the 4B model's: it has fewer KV heads (4 vs 8), which outweighs having more layers (48 vs 36).
- **GPU:** 49/49 layers offloaded (100% GPU, `RUNNER llamacpp`).
- **Speed:**
  - prompt processing ~**2,250 tok/s** on a 719-token prompt, so a 20k-token Claude Code turn would take roughly 9 s, or much less when the prompt cache hits;
  - generation ~**95–99 tok/s**.
- **Load time:** 4.8 s the first time (reading 17 GiB from disk), and 1.5 s when reloaded shortly after, because macOS still had the file cached in memory.
- **Default sampling:** temperature 0.7, top_p 0.8, top_k 20, repeat_penalty 1.05.
- **Licence:** Apache 2.0.

---

## Baseline: Claude Sonnet via ADW (2026-10-18)

- `adw_prompt.py "list the files in apps/"`: 2 turns, 3.4 s, ~39.5k input tokens (mostly cache reads), 136 output tokens.

## Observations

- At 64k context, KV cache size depends on **layers × KV heads**, not on total parameters. Hence the 4B model needs 4.9 GiB of cache and the 30B model only 3.3 GiB.
- q8_0 KV cache saves a lot of memory: at f16, the 4B model's cache would be ~9.6 GiB instead of 4.9 GiB.
- MoE models are the sweet spot for 36 GB. Memory cost scales with *total* parameters, but speed scales with *active* parameters.
- llama.cpp keeps a prompt cache (up to 8 GiB) and reuses a matching prefix across requests. This is the local equivalent of Anthropic's prompt caching, and important for Claude Code's repeated ~20k-token system prompt.
- `ollama stop` is implemented as an empty `/api/generate` call with keep-alive 0. That's why it appears in the server log as a generate request.
- The server binds to 127.0.0.1 only, so it can't be reached from the network. `OLLAMA_NO_CLOUD=1` would turn off Ollama's cloud models.

## Claude Code headless runs on `qwen3-coder:30b`

**2026-10-24.** `claude -p "create fizzbuzz.py and run it" --output-format json`, run from `~/develop` with the default permission mode.

- **Model loading:** none needed. Ollama loads a model on the first request, and `ollama ps` showed it at 22 GB, 100% GPU, afterwards.
- **Timings and tokens:**

  | Measure | Value |
  |---|---|
  | Turns | 8 |
  | Total time | 27.6 s |
  | Time to first token | 11.3 s (first turn processes the whole system prompt) |
  | Input tokens, uncached | ~9.5k |
  | Input tokens, prompt-cache reads | ~68k |
  | Output tokens | 1.4k |

  The first turn is the expensive one. After that the prompt cache does most of the work.
- **Outcome: the task was not done.** Every Write and Bash tool call was **denied**.
  - In `-p` (headless) mode there's nobody to approve permission prompts, so the default mode denies them.
  - The model reacted by trying other paths (`~/fizzbuzz.py`, `/tmp`, an inline `python3 -c`), then gave up and printed the code instead.
- **Wrong directory:** its first attempt wrote to `/Users/phil/fizzbuzz.py`, not the working directory. Expect local models to make more path mistakes. Specs should name exact paths.
- **`"is_error": false, "subtype": "success"` even though the task failed.** "Success" means the session ended normally, not that the work got done. **ADWs must check the outcome themselves** (file exists, tests pass) rather than trust this flag.
- **`total_cost_usd` 0.083** has `"costBasis": "unknown"`. It's an estimate from token counts. Nothing is billed for local runs.
- **Harmless messages:**
  - `claude.ai connectors are disabled ...`: expected, because the auth token takes precedence over your claude.ai login.
  - `[claude-code:unrecognized_model] ... generate_session_title`: Claude Code's background session-title request, also sent to the local model.
- **Fix for the next run:** `cd` into `scratch-local` first, and allow the tools, using either:
  - `--permission-mode acceptEdits --allowedTools "Bash(python3:*)"`, or
  - `--dangerously-skip-permissions` (what the TAC-8 ADWs use; only inside a throwaway or git-tracked repo).

## ADW lifecycle on `qwen3-coder:30b`

**2026-11-01.** One run per profile of `adw_chore_implement.py`, each on a different small README task, so this isn't a fair benchmark.

| Step | `local` | `claude` (Sonnet) |
|---|---|---|
| Plan | 31.2 s, 9 turns | 18.3 s, 4 turns |
| Build | 7.3 s, 1 turn | 18.9 s, 5 turns |
| Commit message | 23.2 s, 6 turns | 3.7 s, 2 turns |
| PR text | 27.0 s, 11 turns | 4.6 s, 2 turns |
| **Total** | **88.6 s** | **45.5 s** |

- **Outcome:** the local model planned and built a correct one-sentence change, and its PR text was valid JSON. This is the first `/chore` → `/implement` cycle run entirely on a local model, on a trivial task.
- **`/commit` is its weak spot:**
  - In one run it added a preamble and invented details, saying `git_ops.py` handles cloning.
  - In another it returned a paragraph with no commit message at all, so the Python fallback wrote the subject.
  - ADWs keep only a valid conventional subject line for this reason. The format is checked, but accuracy isn't.
- **Stray tag:** replies sometimes end with a literal `<tool_call>`. Validate model text rather than using it directly.
- **Split-profile run, planning on Sonnet and building locally:** a one-sentence change took 11.1 s to plan and 23.7 s to build, and the diff was correct.

## To do

- Measure prompt eval with a ~20k-token prompt, which is closer to a real Claude Code turn.
- Phase 1d.2: Claude Code interactively on `qwen3-coder:30b`, with `CLAUDE_CODE_MAX_CONTEXT_TOKENS=65536`. Record tool-call reliability and seconds per turn in the Models tried section.
- Try `gpt-oss:20b` and a Devstral model for comparison.
