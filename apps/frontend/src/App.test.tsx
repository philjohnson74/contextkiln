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

function requestBody(call: number) {
  return JSON.parse(fetchMock.mock.calls[call][1]?.body as string);
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
    expect(requestBody(0)).toEqual({ conversation_id: null, message: "Why is this query slow?" });
  });

  it("sends the conversation id with follow-up messages", async () => {
    fetchMock.mockResolvedValueOnce(ndjson([REPLY]));
    fetchMock.mockResolvedValueOnce(ndjson([REPLY]));
    render(<App />);

    await ask("First");
    await screen.findByText("Add an index.");
    await ask("Second");

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(requestBody(1)).toEqual({ conversation_id: "c1", message: "Second" });
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
    expect(requestBody(1)).toEqual({ conversation_id: "c1" });
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
});
