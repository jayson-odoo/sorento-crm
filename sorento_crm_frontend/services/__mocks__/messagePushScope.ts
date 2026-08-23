/* -------------------------------------------------------------------------------------
 * Phase 1 fixtures for the message push scope preference (PLAN-message-push, S0).
 * One scenario per state the card has to survive, so the prototype can be exercised in a
 * browser before `notify_push_message_scope` exists on the backend.
 *
 * Driven by `?messagePushMock=<scenario>` on /user-management/account:
 *   (absent) | ok    - loads, saves, persists across a reload (AC-M3)
 *   slow_load        - 4s load, to look at the loading state
 *   load_error       - the GET fails; the card offers a retry and keeps the default
 *   save_error       - the PATCH fails with a 422-shaped message (AC-M4)
 *
 * The saved value lives in localStorage so a reload shows what was chosen, which is the
 * half of AC-M3 a purely in-memory stub cannot demonstrate.
 *
 * Deleted in S1 when the service swaps onto the real route.
 * ----------------------------------------------------------------------------------- */

import type { MessagePushScope } from '@/services/messagePushScopeService';

const STORE_KEY = 'mock:notify_push_message_scope';
const SEEDED_SCOPE: MessagePushScope = 'assigned_and_coverage';

const VALID: MessagePushScope[] = [
  'assigned_and_coverage',
  'assigned_only',
  'all_contacts',
  'off',
];

function scenario(): string {
  if (typeof window === 'undefined') return 'ok';
  return new URLSearchParams(window.location.search).get('messagePushMock') || 'ok';
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function read(): MessagePushScope {
  if (typeof window === 'undefined') return SEEDED_SCOPE;
  const stored = window.localStorage.getItem(STORE_KEY);
  return VALID.includes(stored as MessagePushScope)
    ? (stored as MessagePushScope)
    : SEEDED_SCOPE;
}

export async function mockFetchMessagePushScope(): Promise<MessagePushScope> {
  const mode = scenario();
  await delay(mode === 'slow_load' ? 4000 : 400);
  if (mode === 'load_error') {
    throw new Error('Unable to load message notification setting');
  }
  return read();
}

export async function mockSaveMessagePushScope(
  scope: MessagePushScope,
): Promise<MessagePushScope> {
  await delay(500);
  if (scenario() === 'save_error') {
    // Shaped like the 422 the real route returns for a value outside the four.
    throw new Error(`'${scope}' is not a valid message notification scope`);
  }
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(STORE_KEY, scope);
  }
  return scope;
}
