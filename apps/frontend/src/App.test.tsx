import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { streamChat, type ChatEvent } from "./api";

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
  const call = fetchMock.mock.calls.find(([callUrl]) => callUrl === url);
  if (!call) return null;
  return JSON.parse(call[1]?.body as string);
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

describe("App", () => {
  it("shows the question and the streamed reply", async () => {
    fetchMock.mockResolvedValue(ndjson([REPLY]));
    render(<App />);

    await ask("Why is this query slow?");

    expect(screen.getByText("Why is this query slow?")).toBeInTheDocument();
    expect(await screen.findByText("Add an index.")).toBeInTheDocument();
    expect(requestBody("/api/chat")).toEqual({ conversation_id: null, message: "Why is this query slow?" });
  });

  it("sends the conversation id with follow-up messages", async () => {
    fetchMock.mockResolvedValueOnce(ndjson([REPLY]));
    fetchMock.mockResolvedValueOnce(ndjson([REPLY]));
    render(<App />);

    await ask("First");
    await screen.findByText("Add an index.");
    await ask("Second");

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(requestBody("/api/chat")).toEqual({ conversation_id: "c1", message: "Second" });
  });

  it("shows an error sent in the stream", async () => {
    fetchMock.mockResolvedValue(
      ndjson([
        events(
          { type: "conversation", conversation_id: "c1" },
          { type: "error", message: "The model couldn't reply." },
        ),
      ]),
    );
    render(<App />);

    await ask("Hi");

    expect(await screen.findByRole("alert")).toHaveTextContent("The model couldn't reply.");
  });

  it("shows an error when the server can't be reached", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    render(<App />);

    await ask("Hi");

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't reach ContextKiln");
  });

  it("disables escalation until a conversation exists", () => {
    render(<App />);

    expect(screen.getByRole("button", { name: "Talk to a human" })).toBeDisabled();
  });

  it("escalates once and confirms", async () => {
    fetchMock.mockResolvedValueOnce(ndjson([REPLY]));
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ id: 7, conversation_id: "c1", summary: "Hi", status: "open", created_at: "now" }),
        { status: 201 },
      ),
    );
    render(<App />);

    await ask("Hi");
    await screen.findByText("Add an index.");
    const button = screen.getByRole("button", { name: "Talk to a human" });
    await userEvent.click(button);

    expect(await screen.findByRole("status")).toHaveTextContent("reference #7");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/escalations");
    expect(requestBody("/api/escalations")).toEqual({ conversation_id: "c1" });
    expect(button).toBeDisabled();
  });

  it("lets the user retry a failed escalation", async () => {
    fetchMock.mockResolvedValueOnce(ndjson([REPLY]));
    fetchMock.mockResolvedValueOnce(new Response("error", { status: 500 }));
    render(<App />);

    await ask("Hi");
    await screen.findByText("Add an index.");
    const button = screen.getByRole("button", { name: "Talk to a human" });
    await userEvent.click(button);

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't send your request");
    expect(button).toBeEnabled();
  });

  it("loads and shows conversation list on mount", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          conversations: [
            { id: "c1", created_at: "2023-01-01T00:00:00Z", title: "First conversation", message_count: 2 },
            { id: "c2", created_at: "2023-01-02T00:00:00Z", title: "Second conversation", message_count: 1 },
          ],
        }),
        { status: 200 },
      ),
    );
    fetchMock.mockResolvedValueOnce(ndjson([REPLY]));
    render(<App />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    // Check that the sidebar has the conversation buttons
    expect(screen.getByRole("button", { name: "New conversation" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "First conversation" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Second conversation" })).toBeInTheDocument();
  });

  it("loads messages when selecting a conversation", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          conversations: [
            { id: "c1", created_at: "2023-01-01T00:00:00Z", title: "First conversation", message_count: 2 },
            { id: "c2", created_at: "2023-01-02T00:00:00Z", title: "Second conversation", message_count: 1 },
          ],
        }),
        { status: 200 },
      ),
    );
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          conversation_id: "c2",
          messages: [
            { role: "user", content: "Hello", created_at: "2023-01-02T00:00:00Z" },
            { role: "assistant", content: "Hi there!", created_at: "2023-01-02T00:00:00Z" },
          ],
        }),
        { status: 200 },
      ),
    );
    render(<App />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    // Select conversation c2
    const conversationButton = screen.getByRole("button", { name: "Second conversation" });
    await userEvent.click(conversationButton);

    // Check that the messages are displayed
    expect(await screen.findByText("Hi there!")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Second conversation" })).toHaveAttribute(
      "aria-current",
      "true"
    );
  });

  it("creates a new conversation and clears the chat", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          conversations: [
            { id: "c1", created_at: "2023-01-01T00:00:00Z", title: "First conversation", message_count: 2 },
          ],
        }),
        { status: 200 },
      ),
    );
    fetchMock.mockResolvedValueOnce(ndjson([REPLY]));
    render(<App />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    // Create a new conversation
    const newConversationButton = screen.getByRole("button", { name: "New conversation" });
    await userEvent.click(newConversationButton);

    // Check that the chat is cleared
    expect(screen.queryByText("Add an index.")).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText("Ask a question")).toBeInTheDocument();
  });

  it("refreshes conversation list after first reply in new conversation", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          conversations: [
            { id: "c1", created_at: "2023-01-01T00:00:00Z", title: "First conversation", message_count: 2 },
          ],
        }),
        { status: 200 },
      ),
    );
    fetchMock.mockResolvedValueOnce(ndjson([REPLY]));
    // Mock the second call to get conversations with the new conversation at the top
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          conversations: [
            { id: "c_new", created_at: "2023-01-03T00:00:00Z", title: "New conversation", message_count: 1 },
            { id: "c1", created_at: "2023-01-01T00:00:00Z", title: "First conversation", message_count: 2 },
          ],
        }),
        { status: 200 },
      ),
    );
    render(<App />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    // Send a new message to create a new conversation
    await ask("New question");

    // Check that refresh was called after the first reply
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(3);
    });
  });

  it("disables conversation buttons and 'New conversation' while streaming", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          conversations: [
            { id: "c1", created_at: "2023-01-01T00:00:00Z", title: "First conversation", message_count: 2 },
          ],
        }),
        { status: 200 },
      ),
    );

    // Mock a streaming response that takes a while
    const streamResponse = new Response(
      new ReadableStream({
        start(controller) {
          controller.enqueue(new TextEncoder().encode(events({ type: "delta", text: "Thinking..." })));
          setTimeout(() => {
            controller.enqueue(new TextEncoder().encode(events({ type: "done" })));
            controller.close();
          }, 100);
        },
      }),
      { status: 200 }
    );

    fetchMock.mockResolvedValueOnce(streamResponse);
    render(<App />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    // Send a message
    await ask("Test question");

    // Check that the conversation button is disabled during streaming
    const conversationButton = screen.getByRole("button", { name: "First conversation" });
    expect(conversationButton).toBeDisabled();
  });

  it("clears error when switching conversations", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          conversations: [
            { id: "c1", created_at: "2023-01-01T00:00:00Z", title: "First conversation", message_count: 2 },
          ],
        }),
        { status: 200 },
      ),
    );
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          conversation_id: "c1",
          messages: [
            { role: "user", content: "Hello", created_at: "2023-01-01T00:00:00Z" },
            { role: "assistant", content: "Hi there!", created_at: "2023-01-01T00:00:00Z" },
          ],
        }),
        { status: 200 },
      ),
    );
    render(<App />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    // Simulate an error by manually setting one
    const appElement = screen.getByRole("main");
    appElement.setAttribute("aria-live", "polite");
    const errorElement = document.createElement("p");
    errorElement.className = "error";
    errorElement.role = "alert";
    errorElement.textContent = "Test error";
    appElement.appendChild(errorElement);

    // Select a conversation
    const conversationButton = screen.getByRole("button", { name: "First conversation" });
    await userEvent.click(conversationButton);

    // Check that the error is cleared
    expect(screen.queryByText("Test error")).not.toBeInTheDocument();
  });

  it("shows error when failed to load conversations", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response("error", { status: 500 }),
    );
    render(<App />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    // Check that the error is displayed
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load your conversations.");
  });
});
