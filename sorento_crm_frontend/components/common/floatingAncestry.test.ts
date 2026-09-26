/**
 * Chatbot memory lane A browser pass (26 Sep 2026): `Sheet` had no outside-interaction
 * guard at all, unlike `Dialog` - `guardFloatingOutsideInteraction` is the shared
 * implementation both now call, extracted from `dialog.tsx`'s own (previously
 * private) `guardOutsideInteraction` so the two can never drift into two different
 * lists of "what counts as still inside".
 */
import { describe, it, expect, vi } from 'vitest';
import { focusIsInsideFloating, guardFloatingOutsideInteraction } from './floatingAncestry';

function radixOutsideEvent(target: Element): Event {
  // Radix wraps `pointerDownOutside`/`interactOutside`/`focusOutside` in a
  // CustomEvent whose OWN `target` is the surface's content node - the real DOM
  // target lives on `detail.originalEvent.target` (`dialog.tsx`'s own comment).
  const originalEvent = { target } as unknown as Event;
  return new CustomEvent('interactOutside', {
    cancelable: true,
    detail: { originalEvent },
  });
}

describe('focusIsInsideFloating', () => {
  it('is true for a node inside a popover content wrapper', () => {
    document.body.innerHTML = '<div data-radix-popper-content-wrapper><button id="opt">Note</button></div>';
    expect(focusIsInsideFloating(document.getElementById('opt'))).toBe(true);
  });

  it('is true for a node inside a dialog/sheet content slot', () => {
    document.body.innerHTML = '<div data-slot="dialog-content"><button id="save">Save</button></div>';
    expect(focusIsInsideFloating(document.getElementById('save'))).toBe(true);
  });

  it('is false for a node with no floating ancestor', () => {
    document.body.innerHTML = '<div id="page"><button id="plain">Plain</button></div>';
    expect(focusIsInsideFloating(document.getElementById('plain'))).toBe(false);
  });

  it('is false for null', () => {
    expect(focusIsInsideFloating(null)).toBe(false);
  });
});

describe('guardFloatingOutsideInteraction', () => {
  it('prevents default when the real click target is inside a nested floating surface', () => {
    document.body.innerHTML = '<div data-radix-popper-content-wrapper><button id="opt">Note</button></div>';
    const event = radixOutsideEvent(document.getElementById('opt')!);
    const preventDefault = vi.spyOn(event, 'preventDefault');

    guardFloatingOutsideInteraction(event);

    expect(preventDefault).toHaveBeenCalled();
  });

  it('prevents default when the click landed inside another stacked dialog/sheet', () => {
    document.body.innerHTML = '<div data-slot="sheet-content"><button id="ok">OK</button></div>';
    const event = radixOutsideEvent(document.getElementById('ok')!);
    const preventDefault = vi.spyOn(event, 'preventDefault');

    guardFloatingOutsideInteraction(event);

    expect(preventDefault).toHaveBeenCalled();
  });

  it('does nothing for a genuine outside click', () => {
    document.body.innerHTML = '<div id="page"><button id="elsewhere">Elsewhere</button></div>';
    const event = radixOutsideEvent(document.getElementById('elsewhere')!);
    const preventDefault = vi.spyOn(event, 'preventDefault');

    guardFloatingOutsideInteraction(event);

    expect(preventDefault).not.toHaveBeenCalled();
  });
});
