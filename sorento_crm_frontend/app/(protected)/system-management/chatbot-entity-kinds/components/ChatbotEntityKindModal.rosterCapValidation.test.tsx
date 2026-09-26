/**
 * PR #952 review round (reviewer S8, `.claude/handoffs/rearch-phase3-reviewer.md`):
 * `roster_cap` has `min={2}` on the number input, but `min` is advisory only (Save is
 * a click handler, not an HTML form submit) and `handleSave` guards only `code`/`label`
 * - clearing the field (`Number('') === 0`) or typing 0/1/51 currently reaches
 * `create.mutate`/`update.mutate` verbatim and the user gets a raw 422 back from the
 * API's `ge=2` (soon `ge=2, le=50`) validator instead of inline feedback.
 *
 * Beside `ChatbotEntityKindModal.test.tsx` (AC-1711's own roster-cap coverage), not
 * merged into it - a distinct concern (client-side range validation) with its own file
 * per the captain's brief.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ChatbotEntityKind } from '../types/chatbotEntityKind.types';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);
Element.prototype.setPointerCapture = Element.prototype.setPointerCapture ?? (() => {});
Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture ?? (() => {});
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const createMutate = vi.fn();
const updateMutate = vi.fn();
vi.mock('../hooks/useChatbotEntityKinds', () => ({
  useCreateChatbotEntityKind: () => ({ mutate: createMutate, isPending: false }),
  useUpdateChatbotEntityKind: () => ({ mutate: updateMutate, isPending: false }),
}));

import ChatbotEntityKindModal from './ChatbotEntityKindModal';

const PRODUCT_KIND = {
  code: 'product',
  label: 'Product',
  resolved_against: 'products (code, name, family)',
  did_you_mean: true,
  default_narrowing: 'narrow_to_code',
  family_grouping: 'by base code',
  base_property_words: {},
  roster_cap: 7,
} as unknown as ChatbotEntityKind;

function renderModal(props: Partial<React.ComponentProps<typeof ChatbotEntityKindModal>> = {}) {
  return render(
    <ChatbotEntityKindModal
      open
      onOpenChange={vi.fn()}
      entityKindCode={PRODUCT_KIND.code}
      rows={[PRODUCT_KIND]}
      onNavigate={vi.fn()}
      canManage
      {...props}
    />,
  );
}

beforeEach(() => {
  createMutate.mockReset();
  updateMutate.mockReset();
});
afterEach(() => cleanup());

describe('ChatbotEntityKindModal - roster cap client-side range validation (reviewer S8)', () => {
  it.each([0, 1, 51])('typing %s never calls the save mutation', (value) => {
    renderModal();
    const field = screen.getByLabelText(/Roster cap/i) as HTMLInputElement;
    fireEvent.change(field, { target: { value: String(value) } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(updateMutate).not.toHaveBeenCalled();
  });

  it('clearing the field never calls the save mutation with roster_cap: 0', () => {
    renderModal();
    const field = screen.getByLabelText(/Roster cap/i) as HTMLInputElement;
    fireEvent.change(field, { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(updateMutate).not.toHaveBeenCalled();
  });

  it('typing an out-of-range value shows inline validation text', () => {
    renderModal();
    const field = screen.getByLabelText(/Roster cap/i) as HTMLInputElement;
    fireEvent.change(field, { target: { value: '51' } });
    expect(screen.getByText(/between 2 and 50/i)).toBeInTheDocument();
  });

  it('a valid boundary value (2) still saves normally', () => {
    renderModal();
    const field = screen.getByLabelText(/Roster cap/i) as HTMLInputElement;
    fireEvent.change(field, { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(updateMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        code: PRODUCT_KIND.code,
        input: expect.objectContaining({ roster_cap: 2 }),
      }),
      expect.anything(),
    );
  });
});
