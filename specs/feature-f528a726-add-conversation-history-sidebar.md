# Feature: Conversation history sidebar

## Metadata
adw_id: `f528a726`
prompt: `Work on GitHub issue #18. Add a conversation history sidebar to the chat page, so you can see past conversations and pick one up again. Frontend for PLAN.md Phase 6, item 1, using GET /api/conversations/{id}/messages (#14) and GET /api/conversations (#16). No backend changes.`

## Feature Description
Add a left-hand sidebar to the chat page that lists past conversations (newest first, by `title`). Clicking one loads its messages into the chat and makes it the active conversation, so the next message continues it. A "New conversation" button resets the chat to the empty state. After the first reply in a new conversation finishes, the list refreshes so the new conversation appears at the top, highlighted. On screens under 640px the sidebar sits above the chat.

## User Story
As a ContextKiln user
I want to see my past conversations and pick one up again
So that I can continue earlier work without losing context

## Problem Statement
The chat page holds a single in-memory conversation. Reloading the page or starting over loses access to earlier conversations, even though the backend stores them and now exposes list and messages endpoints.

## Solution Statement
Add `listConversations()` and `getMessages(id)` to `api.ts`. Add a `Sidebar` component that renders a `<nav aria-label="Conversations">` with a "New conversation" button and one button per conversation. `App` owns the state (conversation list, active id, messages) and handles load, switch, new and refresh. Selection, new and refresh are all blocked while streaming. Switching resets error, escalation state and the escalating flag. Layout becomes a flex row with a CSS media query for narrow screens.

## Relevant Files
Use these files to implement the feature:

- `apps/frontend/src/api.ts` - add response types and the two fetch helpers, following the style of `createEscalation`.
- `apps/frontend/src/App.tsx` - state, handlers and layout wiring.
- `apps/frontend/src/App.css` - sidebar layout, active-item highlight, narrow-screen rule. `.chat` currently has `max-width: 800px; margin: 0 auto`, which must move to an inner wrapper.
- `apps/frontend/src/App.test.tsx` - new tests; reuse `ndjson`, `events`, `REPLY`, `ask`, `requestBody` helpers. Existing tests use `fetchMock.mockResolvedValue(...)` for every call, so they will now also receive the list request on mount; update them (see task 5).
- `app_docs/app-shell.md` - document the sidebar.
- `apps/backend/app/main.py` - read only, to confirm response shapes: `{conversations: [{id, created_at, title, message_count}]}` and `{conversation_id, messages: [{role, content, created_at}]}`.

### New Files
- `apps/frontend/src/Sidebar.tsx` - presentational sidebar component.

## Implementation Plan
### Phase 1: Foundation
Add API types and helpers in `api.ts`. Both throw an `Error` with the status on a non-OK response.

### Phase 2: Core Implementation
Build `Sidebar` (props: `conversations`, `activeId`, `disabled`, `onSelect(id)`, `onNew()`). Add CSS.

### Phase 3: Integration
Wire into `App`: load the list on mount, `selectConversation`, `newConversation`, refresh after first reply, reset rules, error handling.

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. API helpers
- In `apps/frontend/src/api.ts` add `export interface ConversationSummary { id: string; created_at: string; title: string; message_count: number }` and `export interface StoredMessage { role: "user" | "assistant"; content: string; created_at: string }`.
- Add `listConversations(): Promise<ConversationSummary[]>` that GETs `/api/conversations` and returns `.conversations`; throw `Conversations request failed with status N` if not OK.
- Add `getMessages(id: string): Promise<StoredMessage[]>` that GETs `/api/conversations/${encodeURIComponent(id)}/messages` and returns `.messages`; throw similarly on failure.

### 2. Sidebar component
- Create `apps/frontend/src/Sidebar.tsx`. Render `<nav aria-label="Conversations" className="sidebar">` containing a "New conversation" `<button type="button">` at the top, then a `<ul>` with an `<li><button>` per conversation showing `title`.
- Each conversation button gets `aria-current={id === activeId ? "true" : undefined}` and class `active` when current. All buttons get `disabled={disabled}`.
- Keep the component stateless.

### 3. Styles
- In `App.css`, add an `.app` wrapper: `display: flex; height: 100dvh`. Move `height: 100dvh` from `.chat` to the wrapper; make `.chat` `flex: 1; min-width: 0` and keep its `max-width`/padding (drop `margin: 0 auto` only if it breaks the layout beside the sidebar; otherwise keep it).
- `.sidebar`: fixed width (~240px), `border-right: 1px solid var(--border)`, padding, `overflow-y: auto`, flex column with gap. Conversation buttons: full width, left-aligned, single-line ellipsis truncation. `.sidebar button.active` uses a visible highlight (e.g. `background: var(--reply-bg)` plus a stronger border) using existing CSS variables.
- `@media (max-width: 639px)`: `.app` becomes `flex-direction: column`; `.sidebar` becomes full width with `max-height: 30dvh`, `border-right: none; border-bottom: 1px solid var(--border)`. No toggle or drawer.

### 4. Wire up App
- In `App.tsx` wrap the layout: `<div className="app"><Sidebar .../><main className="chat">…</main></div>`.
- Add state `conversations: ConversationSummary[]`. Add `refreshConversations()` that calls `listConversations()`, sets the list, and on failure sets error `"Couldn't load your conversations."`. Call it in a mount `useEffect`.
- `selectConversation(id)`: return if `streaming` or `id === conversationId`. Use a ref counter (`loadSeq`) so a stale response from an earlier click is ignored. Call `getMessages(id)`; on success set messages (mapped to `{role, content}`), `conversationId`, and reset `error`, `escalationId` (null), `escalating` (false), `input` may be left alone. On failure set error `"Couldn't load that conversation."` and change nothing else (current chat stays).
- `newConversation()`: return if `streaming`; increment `loadSeq` (cancels pending loads), set `messages=[]`, `conversationId=null`, `error=null`, `escalationId=null`, `escalating=false`.
- In `send`, remember `const isNew = conversationId === null` before streaming; after `streamChat` resolves without throwing and without an error event, call `refreshConversations()` when `isNew`. Track error events in a local variable so a failed first reply doesn't refresh needlessly (refresh anyway is acceptable if the backend created the conversation; prefer refreshing when a `conversation` event was received). The refresh must not clear an error set by the stream; it only sets error on its own failure.
- In `escalate`, capture the conversation id and ignore the result if `conversationId` changed meanwhile (use a ref mirroring the active id) so an in-flight escalation can't land in another conversation.
- Pass `disabled={streaming}` to `Sidebar`; also have `selectConversation`/`newConversation` early-return on `streaming` as a guard.

### 5. Tests
- In `App.test.tsx`, add a `route` helper: a `fetchMock.mockImplementation` that dispatches by URL/method (`/api/conversations` GET → list, `/api/conversations/{id}/messages` → messages, `/api/chat` → `ndjson([REPLY])`, `/api/escalations` → JSON). Update existing App tests to use it (default list = empty) since `fetch` is now called on mount; adjust `requestBody(n)` indexing to find the `/api/chat` call by URL instead of by call index.
- Add `api` tests: `listConversations` and `getMessages` return parsed data and throw on error status.
- Add App tests:
  - sidebar lists conversations in API order inside `navigation` named "Conversations".
  - clicking a conversation shows its messages, sets `aria-current="true"` on its button, and the next message posts that `conversation_id`.
  - "New conversation" clears the chat and the next `/api/chat` body has `conversation_id: null`.
  - list refreshes after the first reply in a new conversation (second GET returns the new conversation first; it appears at the top and is `aria-current`).
  - conversation buttons and "New conversation" are disabled while a reply streams (use a controllable `ReadableStream` that is closed later).
  - switching conversations resets escalation: escalate in conversation A, confirmation shows; click B; confirmation gone and "Talk to a human" enabled.
  - switching clears an existing error.
  - failed list load shows `role="alert"`; failed messages load shows an alert and leaves the current chat unchanged.

### 6. Docs
- In `app_docs/app-shell.md`, update the intro line and add a short "Conversation sidebar" section: what it lists, click to resume, New conversation, refresh after first reply, disabled while streaming, error behaviour, narrow-screen layout. Add `Sidebar.tsx` to the Code list and mention the new `api.ts` helpers.

### 7. Validate
- Run the validation commands below and fix failures.

## Testing Strategy
### Unit Tests
Vitest + Testing Library in `App.test.tsx` with `fetch` mocked; no real backend or model.

### Edge Cases
- Empty conversation list (no items, "New conversation" still shown).
- Clicking the already-open conversation does nothing.
- Rapid clicks on two conversations: only the last response is applied.
- Failed load leaves messages, active id and escalation state untouched.
- "New conversation" while a messages load is pending cancels that load.
- Failed first reply: no spurious state changes; error preserved.
- Escalation in flight when switching does not appear in the new conversation.

## Acceptance Criteria
- The sidebar shows conversations from `GET /api/conversations` in API order, using `<nav aria-label="Conversations">` with one button each.
- Clicking one loads its messages and the next send includes its `conversation_id`; its button has `aria-current="true"`.
- "New conversation" returns to the empty state and the next send has `conversation_id: null`.
- After the first reply in a new conversation the list refreshes with it on top and highlighted.
- Conversation buttons and "New conversation" are disabled while streaming.
- Switching clears error and resets "Talk to a human" and the escalation confirmation.
- List/message load failures show a `role="alert"` error and leave the current chat as is.
- Under 640px the sidebar sits above the chat; no toggle or drawer.
- No backend changes and no new npm dependencies; `app_docs/app-shell.md` updated.

## Validation Commands
Execute these commands to validate the feature is complete:

- `cd apps/frontend && npm test` - Run the frontend tests
- `cd apps/frontend && npx tsc --noEmit` - Type-check (or `npm run build` if that is the project's check)
- `./scripts/test.sh` - Run all tests

## Notes
- The backend titles are derived from the first user message, so no title editing or deletion is in scope.
- Deliberately out of scope: pagination, search, deleting conversations, persisting the active conversation across reloads.
- Follow the repo rules: agents don't run git or gh; keep changes to what this plan asks for.
