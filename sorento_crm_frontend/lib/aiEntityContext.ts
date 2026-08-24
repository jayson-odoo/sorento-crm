/**
 * aiEntityContext - module-level store of the record the user is currently
 * viewing/editing, used to ground the AI assistant's answers.
 *
 * Why a module store (not React context): the page snapshot is built by the
 * plain imperative `getPageSnapshot()` (lib/aiPageSnapshot.ts), called at
 * send-time from the bubble - it is NOT inside the React tree, so it can't read
 * a context. A module-level mutable cell lets it read the active entity
 * synchronously at send-time.
 *
 * Set it on mount of a detail page (via <RecordEntityRegistrar/>) AND on
 * modal open; clear on unmount / modal close so a stale record never leaks into
 * an unrelated question.
 */

export interface AIEntityRef {
  entity_type: string;
  id: string;
}

let currentEntity: AIEntityRef | null = null;

export function setCurrentEntity(entity: AIEntityRef | null): void {
  currentEntity = entity;
}

export function clearCurrentEntity(): void {
  currentEntity = null;
}

export function getCurrentEntity(): AIEntityRef | null {
  return currentEntity;
}
