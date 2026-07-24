import '@testing-library/jest-dom';

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
