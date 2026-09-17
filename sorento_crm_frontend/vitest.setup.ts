import '@testing-library/jest-dom';
import { configure } from '@testing-library/dom';
import { MotionGlobalConfig } from 'motion/react';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

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
// mount - so any test touching the standard searchable dropdowns dies with a ReferenceError
// before it can assert anything. Stub them globally rather than per-test file.
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

// Same story for matchMedia: jsdom has none, and the DataGrid asks it whether it
// is under `sm` (to pin the identifier column) on every render. A test that never
// mentions responsiveness would otherwise die in a passive effect. Defaults to
// "no match", i.e. a desktop viewport; a test that cares overrides it.
//
// `prefers-reduced-motion` is the one exception: it defaults to MATCHING (S8-01).
// Dialog/Sheet/Popover/DropdownMenu now open and close on a real JS spring
// (motion/react's AnimatePresence), which - unlike the CSS `animate-in` classes
// it replaced - genuinely ticks over wall-clock time even in jsdom. A suite that
// never mentions motion would otherwise pay a spring's settle time on every
// dialog it opens or closes; a test that specifically cares about the spring
// overrides matchMedia locally (see lib/motion.test.ts).
if (typeof window !== 'undefined' && !window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: query.includes('prefers-reduced-motion'),
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

// The reduced-motion default above shortens every surface transition to 0.01s;
// it does not remove it. An exit still has to start, tick and finish before
// AnimatePresence unmounts the surface, and while a Dialog or AlertDialog is
// mid-exit Radix keeps `aria-hidden` on everything outside it - so a synchronous
// `getByRole` for a button on the page BEHIND a just-closed dialog finds nothing.
// It is a race, so it passes on an idle machine and fails on a loaded one (CI).
//
// `skipAnimations` makes motion apply the final keyframe and report completion
// instead of animating, so a closed surface is gone by the time the next
// assertion runs. A test that cares about the spring asserts the transition it
// was handed rather than an in-flight value (see lib/motion.test.ts); the one
// test that has to read a value motion actually wrote turns this back off for
// its own duration (see components/ui/command.test.tsx).
MotionGlobalConfig.skipAnimations = true;

if (typeof Element !== 'undefined') {
  Element.prototype.scrollIntoView ??= function scrollIntoView() {};
  Element.prototype.hasPointerCapture ??= function hasPointerCapture() {
    return false;
  };
  Element.prototype.setPointerCapture ??= function setPointerCapture() {};
  Element.prototype.releasePointerCapture ??= function releasePointerCapture() {};
}

// A test file that ends with a Radix DropdownMenu / Dialog / Popover / Sheet still open leaves
// FocusScope's unmount effect pending: its cleanup does `setTimeout(() => dispatchEvent(new
// CustomEvent(...)), 0)` against the container node. Testing Library's own auto cleanup unmounts
// the surface after the last test in the file, which arms that timer - but on a loaded CI runner
// vitest can tear the jsdom environment down before the 0ms timer fires, so the CustomEvent gets
// built against an already-dead realm and jsdom's dispatchEvent throws "parameter 1 is not of
// type 'Event'". It is timing-dependent, so it passes locally and fails only on CI, and it looks
// like a bug in whichever test happened to run last rather than in the surface it left open.
//
// Call `cleanup()` here (idempotent alongside Testing Library's own afterEach, and this one is
// guaranteed to run before the drain below regardless of vitest's afterEach ordering) and then
// drain one real macrotask so FocusScope's timer fires while the window is still alive. Skip the
// drain under fake timers: a fake timer never fires on its own, so there is nothing to race, and
// awaiting a real setTimeout while timers are faked would just hang.
afterEach(async () => {
  cleanup();
  if (vi.isFakeTimers()) return;
  await new Promise<void>((resolve) => setTimeout(resolve, 0));
});
