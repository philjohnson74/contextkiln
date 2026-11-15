import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { getMessages, listConversations, streamChat, type ChatEvent } from "./api";

const fetchMock = vi.fn<typeof fetch>();

function ndjson(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });
  return new Response(body, { status: 200 });
}

function events(...items: ChatEvent[]): string {
  return items.map((item) => JSON.stringify(item) + "\n").join("");
}

const REPLY = events(
  { type: "conversation", conversation_id: "c1" },
  { type: "delta", text: "Add " },
  { type: "delta", text: "an index." },
  { type: "done" },
);

async function ask(message: string) {
  await userEvent.type(screen.getByLabelText("Message"), message);
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
}

function requestBody(url: string) {
  const call = fetchMock.mock.calls.filter(([callUrl]) => callUrl === url).at(-1);
  if (!call) return null;
  return JSON.parse(call[1]?.body as string);
}

interface Summary {
  id: string;
  created_at: string;
  title: string;
  message_count: number;
}

function summary(id: string, title: string): Summary {
  return { id, created_at: "2023-01-01T00:00:00Z", title, message_count: 2 };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

function storedMessages(id: string, ...pairs: [string, string][]) {
  return {
    conversation_id: id,
    messages: pairs.map(([role, content]) => ({ role, content, created_at: "2023-01-01T00:00:00Z" })),
  };
}

interface Routes {
  lists?: Summary[][]; // successive GET /api/conversations responses; the last one repeats
  listStatus?: number;
  messages?: Record<string, () => Response | Promise<Response>>;
  chat?: () => Response | Promise<Response>;
  escalation?: () => Response | Promise<Response>;
}

function route(routes: Routes = {}) {
  let listCalls = 0;
  fetchMock.mockImplementation(async (input) => {
    const url = String(input);
    if (url === "/api/conversations") {
      if (routes.listStatus) return new Response("error", { status: routes.listStatus });
      const lists = routes.lists ?? [[]];
      const list = lists[Math.min(listCalls++, lists.length - 1)];
      return json({ conversations: list });
    }
    const match = url.match(/^\/api\/conversations\/([^/]+)\/messages$/);
    if (match) {
      const handler = routes.messages?.[decodeURIComponent(match[1])];
      return handler ? handler() : new Response("missing", { status: 404 });
    }
    if (url === "/api/chat") return routes.chat ? routes.chat() : ndjson([REPLY]);
    if (url === "/api/escalations") {
      return routes.escalation
        ? routes.escalation()
        : json({ id: 7, conversation_id: "c1", summary: "Hi", status: "open", created_at: "now" }, 201);
    }
    throw new Error(`Unexpected fetch: ${url}`);
  });
}

function callsTo(url: string) {
  return fetchMock.mock.calls.filter(([callUrl]) => callUrl === url);
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("streamChat", () => {
  it("parses events split across network chunks", async () => {
    const line = events({ type: "delta", text: "héllo" });
    fetchMock.mockResolvedValue(ndjson([line.slice(0, 10), line.slice(10), events({ type: "done" })]));

    const received: ChatEvent[] = [];
    await streamChat("Hi", null, (event) => received.push(event));

    expect(received).toEqual([{ type: "delta", text: "héllo" }, { type: "done" }]);
  });

  it("throws on an error status", async () => {
    fetchMock.mockResolvedValue(new Response("nope", { status: 404 }));

    await expect(streamChat("Hi", "gone", () => {})).rejects.toThrow("404");
  });
});

describe("listConversations", () => {
  it("returns the parsed conversations", async () => {
    fetchMock.mockResolvedValue(json({ conversations: [summary("c1", "One")] }));

    await expect(listConversations()).resolves.toEqual([summary("c1", "One")]);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/conversations");
  });

  it("throws on an error status", async () => {
    fetchMock.mockResolvedValue(new Response("nope", { status: 500 }));

    await expect(listConversations()).rejects.toThrow("500");
  });
});

describe("getMessages", () => {
  it("returns the parsed messages", async () => {
    const body = storedMessages("a/b", ["user", "Hi"]);
    fetchMock.mockResolvedValue(json(body));

    await expect(getMessages("a/b")).resolves.toEqual(body.messages);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/conversations/a%2Fb/messages");
  });

  it("throws on an error status", async () => {
    fetchMock.mockResolvedValue(new Response("nope", { status: 404 }));

    await expect(getMessages("gone")).rejects.toThrow("404");
  });
});

describe("App", () => {
  it("shows the question and the streamed reply", async () => {
    route();
    render(<App />);

    await ask("Why is this query slow?");

    expect(screen.getByText("Why is this query slow?")).toBeInTheDocument();
    expect(await screen.findByText("Add an index.")).toBeInTheDocument();
    expect(requestBody("/api/chat")).toEqual({ conversation_id: null, message: "Why is this query slow?" });
  });

  it("sends the conversation id with follow-up messages", async () => {
    route();
    render(<App />);

    await ask("First");
    await screen.findByText("Add an index.");
    await ask("Second");

    await waitFor(() => expect(callsTo("/api/chat")).toHaveLength(2));
    expect(requestBody("/api/chat")).toEqual({ conversation_id: "c1", message: "Second" });
  });

  it("shows an error sent in the stream and does not refresh the list", async () => {
    route({
      chat: () => ndjson([events({ type: "error", message: "The model couldn't reply." })]),
    });
    render(<App />);

    await ask("Hi");

    expect(await screen.findByRole("alert")).toHaveTextContent("The model couldn't reply.");
    expect(callsTo("/api/conversations")).toHaveLength(1);
  });

  it("keeps a stream error after refreshing the list", async () => {
    route({
      chat: () =>
        ndjson([
          events({ type: "conversation", conversation_id: "c1" }, { type: "error", message: "The model couldn't reply." }),
        ]),
    });
    render(<App />);

    await ask("Hi");

    await waitFor(() => expect(callsTo("/api/conversations")).toHaveLength(2));
    expect(screen.getByRole("alert")).toHaveTextContent("The model couldn't reply.");
  });

  it("shows an error when the server can't be reached", async () => {
    route({ chat: () => Promise.reject(new TypeError("Failed to fetch")) });
    render(<App />);

    await ask("Hi");

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't reach ContextKiln");
  });

  it("disables escalation until a conversation exists", () => {
    route();
    render(<App />);

    expect(screen.getByRole("button", { name: "Talk to a human" })).toBeDisabled();
  });

  it("escalates once and confirms", async () => {
    route();
    render(<App />);

    await ask("Hi");
    await screen.findByText("Add an index.");
    const button = screen.getByRole("button", { name: "Talk to a human" });
    await userEvent.click(button);

    expect(await screen.findByRole("status")).toHaveTextContent("reference #7");
    expect(requestBody("/api/escalations")).toEqual({ conversation_id: "c1" });
    expect(button).toBeDisabled();
  });

  it("lets the user retry a failed escalation", async () => {
    route({ escalation: () => new Response("error", { status: 500 }) });
    render(<App />);

    await ask("Hi");
    await screen.findByText("Add an index.");
    const button = screen.getByRole("button", { name: "Talk to a human" });
    await userEvent.click(button);

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't send your request");
    expect(button).toBeEnabled();
  });

  it("lists conversations in API order inside the Conversations navigation", async () => {
    route({ lists: [[summary("c2", "Second conversation"), summary("c1", "First conversation")]] });
    render(<App />);

    const nav = await screen.findByRole("navigation", { name: "Conversations" });
    const buttons = (await within(nav).findAllByRole("button")).map((b) => b.textContent);
    expect(buttons).toEqual(["New conversation", "Second conversation", "First conversation"]);
  });

  it("shows an empty sidebar with a New conversation button", async () => {
    route();
    render(<App />);

    const nav = await screen.findByRole("navigation", { name: "Conversations" });
    expect(within(nav).getAllByRole("button")).toHaveLength(1);
    expect(within(nav).getByRole("button", { name: "New conversation" })).toBeEnabled();
  });

  it("loads a conversation's messages and continues it", async () => {
    route({
      lists: [[summary("c2", "Second conversation"), summary("c1", "First conversation")]],
      messages: { c2: () => json(storedMessages("c2", ["user", "Hello"], ["assistant", "Hi there!"])) },
    });
    render(<App />);

    await userEvent.click(await screen.findByRole("button", { name: "Second conversation" }));

    expect(await screen.findByText("Hi there!")).toBeInTheDocument();
    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Second conversation" })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("button", { name: "First conversation" })).not.toHaveAttribute("aria-current");

    await ask("Next");
    await waitFor(() => expect(callsTo("/api/chat")).toHaveLength(1));
    expect(requestBody("/api/chat")).toEqual({ conversation_id: "c2", message: "Next" });
  });

  it("does nothing when clicking the already-open conversation", async () => {
    route({
      lists: [[summary("c1", "First conversation")]],
      messages: { c1: () => json(storedMessages("c1", ["user", "Hello"])) },
    });
    render(<App />);

    const button = await screen.findByRole("button", { name: "First conversation" });
    await userEvent.click(button);
    await screen.findByText("Hello");
    await userEvent.click(button);

    expect(callsTo("/api/conversations/c1/messages")).toHaveLength(1);
  });

  it("starts a new conversation with a cleared chat", async () => {
    route({ lists: [[summary("c1", "First conversation")]] });
    render(<App />);

    await ask("Hi");
    await screen.findByText("Add an index.");
    await userEvent.click(screen.getByRole("button", { name: "New conversation" }));

    expect(screen.queryByText("Add an index.")).not.toBeInTheDocument();
    expect(screen.getByText("Ask a software engineering or infrastructure question.")).toBeInTheDocument();

    await ask("Again");
    await waitFor(() => expect(callsTo("/api/chat")).toHaveLength(2));
    expect(requestBody("/api/chat")).toEqual({ conversation_id: null, message: "Again" });
  });

  it("refreshes the list after the first reply and highlights the new conversation", async () => {
    route({
      lists: [[summary("c0", "Older")], [summary("c1", "New question"), summary("c0", "Older")]],
    });
    render(<App />);
    await screen.findByRole("button", { name: "Older" });

    await ask("New question");

    const nav = screen.getByRole("navigation", { name: "Conversations" });
    await waitFor(() => expect(within(nav).getAllByRole("button")[1]).toHaveTextContent("New question"));
    expect(within(nav).getByRole("button", { name: "New question" })).toHaveAttribute("aria-current", "true");
    expect(callsTo("/api/conversations")).toHaveLength(2);
  });

  it("disables the sidebar while a reply streams", async () => {
    let finish!: () => void;
    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode(events({ type: "conversation", conversation_id: "c9" })));
        finish = () => {
          controller.enqueue(encoder.encode(events({ type: "done" })));
          controller.close();
        };
      },
    });
    route({ lists: [[summary("c1", "First conversation")]], chat: () => new Response(body, { status: 200 }) });
    render(<App />);
    await screen.findByRole("button", { name: "First conversation" });

    await ask("Hi");

    expect(screen.getByRole("button", { name: "First conversation" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "New conversation" })).toBeDisabled();

    finish();
    await waitFor(() => expect(screen.getByRole("button", { name: "New conversation" })).toBeEnabled());
  });

  it("resets escalation when switching conversations", async () => {
    route({
      lists: [[summary("c1", "First conversation"), summary("c2", "Second conversation")]],
      messages: {
        c1: () => json(storedMessages("c1", ["user", "A"])),
        c2: () => json(storedMessages("c2", ["user", "B"])),
      },
    });
    render(<App />);

    await userEvent.click(await screen.findByRole("button", { name: "First conversation" }));
    await screen.findByText("A");
    await userEvent.click(screen.getByRole("button", { name: "Talk to a human" }));
    expect(await screen.findByRole("status")).toHaveTextContent("reference #7");

    await userEvent.click(screen.getByRole("button", { name: "Second conversation" }));
    await screen.findByText("B");

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Talk to a human" })).toBeEnabled();
  });

  it("ignores an escalation that finishes after switching conversations", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    route({
      lists: [[summary("c1", "First conversation"), summary("c2", "Second conversation")]],
      messages: {
        c1: () => json(storedMessages("c1", ["user", "A"])),
        c2: () => json(storedMessages("c2", ["user", "B"])),
      },
      escalation: async () => {
        await gate;
        return json({ id: 7, conversation_id: "c1", summary: "A", status: "open", created_at: "now" }, 201);
      },
    });
    render(<App />);

    await userEvent.click(await screen.findByRole("button", { name: "First conversation" }));
    await screen.findByText("A");
    await userEvent.click(screen.getByRole("button", { name: "Talk to a human" }));
    await userEvent.click(screen.getByRole("button", { name: "Second conversation" }));
    await screen.findByText("B");

    release();
    await waitFor(() => expect(callsTo("/api/escalations")).toHaveLength(1));
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Talk to a human" })).toBeEnabled();
  });

  it("clears an existing error when switching conversations", async () => {
    route({
      lists: [[summary("c1", "First conversation")]],
      chat: () => ndjson([events({ type: "error", message: "Test error" })]),
      messages: { c1: () => json(storedMessages("c1", ["user", "Hello"])) },
    });
    render(<App />);
    await screen.findByRole("button", { name: "First conversation" });

    await ask("Hi");
    expect(await screen.findByRole("alert")).toHaveTextContent("Test error");

    await userEvent.click(screen.getByRole("button", { name: "First conversation" }));
    await screen.findByText("Hello");

    expect(screen.queryByText("Test error")).not.toBeInTheDocument();
  });

  it("only applies the last of several rapid conversation clicks", async () => {
    let releaseFirst!: () => void;
    const slow = new Promise<void>((resolve) => (releaseFirst = resolve));
    route({
      lists: [[summary("c1", "First conversation"), summary("c2", "Second conversation")]],
      messages: {
        c1: async () => {
          await slow;
          return json(storedMessages("c1", ["user", "From first"]));
        },
        c2: () => json(storedMessages("c2", ["user", "From second"])),
      },
    });
    render(<App />);

    await userEvent.click(await screen.findByRole("button", { name: "First conversation" }));
    await userEvent.click(screen.getByRole("button", { name: "Second conversation" }));
    await screen.findByText("From second");
    releaseFirst();
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(screen.queryByText("From first")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Second conversation" })).toHaveAttribute("aria-current", "true");
  });

  it("cancels a pending load when starting a new conversation", async () => {
    let release!: () => void;
    const slow = new Promise<void>((resolve) => (release = resolve));
    route({
      lists: [[summary("c1", "First conversation")]],
      messages: {
        c1: async () => {
          await slow;
          return json(storedMessages("c1", ["user", "Late"]));
        },
      },
    });
    render(<App />);

    await userEvent.click(await screen.findByRole("button", { name: "First conversation" }));
    await userEvent.click(screen.getByRole("button", { name: "New conversation" }));
    release();
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(screen.queryByText("Late")).not.toBeInTheDocument();
  });

  it("shows an error when the conversation list fails to load", async () => {
    route({ listStatus: 500 });
    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load your conversations.");
  });

  it("shows an error and keeps the current chat when messages fail to load", async () => {
    route({ lists: [[summary("c2", "Second conversation")]] });
    render(<App />);

    await ask("Hi");
    await screen.findByText("Add an index.");
    await userEvent.click(await screen.findByRole("button", { name: "Second conversation" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load that conversation.");
    expect(screen.getByText("Add an index.")).toBeInTheDocument();
  });
});
