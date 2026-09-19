/**
 * ============================================================================
 * Chatbot Entity kinds service (chatbot turn re-architecture, S5, AC-1560/AC-1561)
 * ============================================================================
 * Layering: UI -> hooks (useChatbotEntityKinds) -> THIS service -> lib/api -> backend.
 *
 *   GET  /api/v1/system/chatbot/entity-kinds            list, `system.chat_history.view`
 *   POST /api/v1/system/chatbot/entity-kinds             create, `system.chatbot_config.manage`
 *   PUT  /api/v1/system/chatbot/entity-kinds/{code}       update, `system.chatbot_config.manage`
 *
 * No delete route (UAC AC-1512 does not ask for one, unlike domains' AC-1511).
 *
 * The backend's field names differ from this screen's own wording (`kind` not `code`,
 * `resolver_source` not "resolved against") - `toWire`/`fromWire` below are the one seam
 * that translates, so the UI keeps the words a reader recognises without the API having
 * to carry two names for the same column.
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { ChatbotEntityKind, ChatbotEntityKindInput } from '../types/chatbotEntityKind.types';

const BASE = '/api/v1/system/chatbot/entity-kinds';

interface ChatbotEntityKindWire {
  kind: string;
  label: string | null;
  resolver_source: string;
  did_you_mean: boolean;
  default_narrowing: ChatbotEntityKind['default_narrowing'];
  family_grouping: string | null;
  base_property_words: Record<string, string>;
  roster_cap: number;
}

function fromWire(row: ChatbotEntityKindWire): ChatbotEntityKind {
  return {
    code: row.kind,
    label: row.label ?? row.kind,
    resolved_against: row.resolver_source,
    did_you_mean: row.did_you_mean,
    default_narrowing: row.default_narrowing,
    family_grouping: row.family_grouping,
    base_property_words: row.base_property_words ?? {},
    roster_cap: row.roster_cap,
  };
}

function toWire(input: ChatbotEntityKindInput): ChatbotEntityKindWire {
  return {
    kind: input.code,
    label: input.label,
    resolver_source: input.resolved_against,
    did_you_mean: input.did_you_mean,
    default_narrowing: input.default_narrowing,
    family_grouping: input.family_grouping,
    base_property_words: input.base_property_words,
    roster_cap: input.roster_cap ?? 10,
  };
}

interface ChatbotEntityKindListResponse {
  data: ChatbotEntityKindWire[];
  pagination: { total: number; page: number; limit: number };
}

export async function listChatbotEntityKinds(): Promise<ChatbotEntityKind[]> {
  const response = await apiFetch(`${BASE}?limit=200&sort=kind&dir=asc`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load entity kinds'));
  }
  const body: ChatbotEntityKindListResponse = await response.json();
  return body.data.map(fromWire);
}

export async function getChatbotEntityKind(code: string): Promise<ChatbotEntityKind | undefined> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(code)}`);
  if (response.status === 404) return undefined;
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the entity kind'));
  }
  return fromWire(await response.json());
}

export async function createChatbotEntityKind(
  input: ChatbotEntityKindInput,
): Promise<ChatbotEntityKind> {
  const response = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(toWire(input)),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to create the entity kind'));
  }
  return fromWire(await response.json());
}

export async function updateChatbotEntityKind(
  code: string,
  input: ChatbotEntityKindInput,
): Promise<ChatbotEntityKind> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(code)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(toWire(input)),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save the entity kind'));
  }
  return fromWire(await response.json());
}
