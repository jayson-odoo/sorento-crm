import '@testing-library/jest-dom';
import { configure } from '@testing-library/dom';

/*
  Testing Library gives an async assertion one second to come true.

  That is a fine budget on an idle machine and not one on a loaded one: running
  the dealer-kit suite as a whole produced six failures that every one of them
  passed alone, across three unrelated files. A timeout that depends on how busy
  the machine is does not test anything - it reports load - and the cost of it
  is that a real regression is indistinguishable from a slow afternoon.

  Five seconds. A test that genuinely fails still fails; it just takes four
  seconds longer to say so, which happens far less often than the false alarm
  did.
*/
configure({ asyncUtilTimeout: 5000 });

// jsdom implements none of these, but cmdk (Command) and Radix (Popover) both call them on
// mount — so any test touching the standard searchable dropdowns dies with a ReferenceError
// before it can assert anything. Stub them globally rather than per-test file.
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

if (typeof Element !== 'undefined') {
  Element.prototype.scrollIntoView ??= function scrollIntoView() {};
  Element.prototype.hasPointerCapture ??= function hasPointerCapture() {
    return false;
  };
  Element.prototype.setPointerCapture ??= function setPointerCapture() {};
  Element.prototype.releasePointerCapture ??= function releasePointerCapture() {};
}
