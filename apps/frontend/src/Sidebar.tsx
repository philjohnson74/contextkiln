import { type ConversationSummary } from "./api";

interface SidebarProps {
  conversations: ConversationSummary[];
  activeId: string | null;
  disabled: boolean;
  onSelect(id: string): void;
  onNew(): void;
}

export function Sidebar({ conversations, activeId, disabled, onSelect, onNew }: SidebarProps) {
  return (
    <nav aria-label="Conversations" className="sidebar">
      <button type="button" onClick={onNew} disabled={disabled}>
        New conversation
      </button>
      <ul>
        {conversations.map((conversation) => (
          <li key={conversation.id}>
            <button
              type="button"
              onClick={() => onSelect(conversation.id)}
              disabled={disabled}
              aria-current={activeId === conversation.id ? "true" : undefined}
              className={activeId === conversation.id ? "active" : ""}
            >
              {conversation.title}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
