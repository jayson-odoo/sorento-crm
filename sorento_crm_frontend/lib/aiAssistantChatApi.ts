import { apiFetch } from '@/lib/api';

export interface AIAssistantMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  metadata_json: {
    links?: string[];
    sources?: Array<{ title?: string }>;
    selected_tools?: Array<{ tool_name?: string }>;
  };
  created_at: string;
}

export interface AIAssistantConversation {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  messages: AIAssistantMessage[];
}

export async function sendAIAssistantMessage(message: string, conversationId?: string) {
  const r = await apiFetch('/api/v1/system/ai-assistant/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      conversation_id: conversationId || null,
    }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to chat with AI assistant');
  }
  return (await r.json()) as AIAssistantConversation;
}
