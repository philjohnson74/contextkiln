export type ChatEvent =
  | { type: "conversation"; conversation_id: string }
  | { type: "delta"; text: string }
  | { type: "done" }
  | { type: "error"; message: string };

export interface Escalation {
  id: number;
  conversation_id: string;
  summary: string;
  status: string;
  created_at: string;
}

/** Send a message and call `onEvent` for each NDJSON event in the reply. */
export async function streamChat(
  message: string,
  conversationId: string | null,
  onEvent: (event: ChatEvent) => void,
): Promise<void> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: conversationId, message }),
  });
  if (!response.ok || !response.body) {
    throw new Error(`Chat request failed with status ${response.status}`);
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    // A network chunk can end partway through a line, so keep the tail for next time.
    buffer += value;
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line.trim()) onEvent(JSON.parse(line) as ChatEvent);
    }
  }
}

export async function createEscalation(conversationId: string): Promise<Escalation> {
  const response = await fetch("/api/escalations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: conversationId }),
  });
  if (!response.ok) {
    throw new Error(`Escalation failed with status ${response.status}`);
  }
  return (await response.json()) as Escalation;
}
