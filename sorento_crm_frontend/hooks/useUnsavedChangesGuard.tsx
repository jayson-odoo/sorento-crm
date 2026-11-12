'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

/** Where a same-site link click would go, or null when the guard should let the click through. */
function guardedHref(event: MouseEvent): string | null {
  if (event.defaultPrevented || event.button !== 0) return null;
  // Ctrl/Cmd/Shift/Alt click opens a new tab or window: this page stays, nothing is lost.
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return null;
  const link = (event.target as Element | null)?.closest?.('a[href]');
  if (!(link instanceof HTMLAnchorElement)) return null;
  if (link.target && link.target !== '_self') return null;
  if (link.hasAttribute('download')) return null;
  const url = new URL(link.href, window.location.href);
  if (url.origin !== window.location.origin) return null;
  const here = window.location;
  // A link to a spot on this same page leaves nothing behind.
  if (url.pathname === here.pathname && url.search === here.search) return null;
  return `${url.pathname}${url.search}${url.hash}`;
}

/**
 * The one shared guard for a page holding unsaved work (crew ruling 11 Nov 2026). While `dirty`:
 * - a same-site link click (back link, breadcrumb, sidebar, another record) asks first;
 * - the browser's Back asks first: the guard keeps one history entry on top of the page, so Back
 *   lands on the page again and the question opens instead (Next's app router has no cancellable
 *   navigation event to hang this on);
 * - a refresh or closing the tab gets the browser's own `beforeunload` prompt.
 * Once `dirty` turns false (saved), the history entry is given back so Back needs one press.
 *
 * Returns the question's dialog: render it anywhere in the page.
 */
export function useUnsavedChangesGuard(
  dirty: boolean,
  {
    fallbackHref,
  }: {
    /** Where Leave goes after the browser's Back when this tab has no earlier page. */
    fallbackHref?: string;
  } = {},
): React.ReactNode {
  const router = useRouter();
  /** Where the user was going: a link's href, or 'back' for the browser's Back. */
  const [leaveTo, setLeaveToState] = React.useState<string | null>(null);
  // Mirrored in a ref: the dialog's button click and its close event both answer the question,
  // and only the first one may act.
  const leaveToRef = React.useRef<string | null>(null);
  const setLeaveTo = React.useCallback((next: string | null) => {
    leaveToRef.current = next;
    setLeaveToState(next);
  }, []);
  /** The guard's history entry is on top of the page. */
  const trappedRef = React.useRef(false);
  /** The next popstate is the guard's own history.back(), not the user's. */
  const ownBackRef = React.useRef(false);
  const dirtyRef = React.useRef(dirty);
  dirtyRef.current = dirty;

  const trap = React.useCallback(() => {
    if (trappedRef.current) return;
    // The current state is copied, so Next's router reads the entry as this same page.
    const state = window.history.state ?? {};
    window.history.pushState(state, '', window.location.href);
    trappedRef.current = true;
  }, []);

  const release = React.useCallback(() => {
    if (!trappedRef.current) return;
    trappedRef.current = false;
    ownBackRef.current = true;
    window.history.back();
  }, []);

  // Arm with the first unsaved change; give the history entry back once it is saved.
  React.useEffect(() => {
    if (dirty) trap();
    else release();
  }, [dirty, trap, release]);

  // Refresh, close, a jump to another site.
  React.useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      // Chrome ignores the text and shows its own; assigning it is what arms the prompt.
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [dirty]);

  // Same-site link clicks. Capture phase on the window, so it runs before Next's <Link> handler.
  React.useEffect(() => {
    if (!dirty) return;
    const onClick = (event: MouseEvent) => {
      const href = guardedHref(event);
      if (href === null) return;
      event.preventDefault();
      event.stopPropagation();
      setLeaveTo(href);
    };
    window.addEventListener('click', onClick, true);
    return () => window.removeEventListener('click', onClick, true);
  }, [dirty, setLeaveTo]);

  // The browser's Back pops the guard's entry: ask, or pass the guard's own back through.
  React.useEffect(() => {
    const onPopState = () => {
      if (ownBackRef.current) {
        ownBackRef.current = false;
        return;
      }
      if (!trappedRef.current) return;
      trappedRef.current = false;
      if (dirtyRef.current) setLeaveTo('back');
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, [setLeaveTo]);

  const stay = () => {
    const target = leaveToRef.current;
    if (target === null) return;
    setLeaveTo(null);
    // Back already used the entry up: put it back so the next Back asks again.
    if (target === 'back' && dirtyRef.current) trap();
  };

  const leave = () => {
    const target = leaveToRef.current;
    setLeaveTo(null);
    if (target === null) return;
    if (target === 'back') {
      // The guard's entry is already gone: this Back reaches the page before this one. A tab
      // opened on this page has none, and Back then goes nowhere: go to the fallback instead.
      // In this app the page before is the same document (Next's router), so the address
      // changes at once and 400 ms only decides "Back went nowhere". Known trade-off: a Back that
      // starts a full page load slower than 400 ms (another site) could be overtaken by this.
      ownBackRef.current = true;
      const from = window.location.href;
      window.history.back();
      if (fallbackHref) {
        window.setTimeout(() => {
          if (window.location.href !== from) return;
          ownBackRef.current = false;
          router.replace(fallbackHref);
        }, 400);
      }
      return;
    }
    // Over the guard's entry, so Back from there returns here once, not twice.
    if (trappedRef.current) {
      trappedRef.current = false;
      router.replace(target);
    } else {
      router.push(target);
    }
  };

  return (
    <AlertDialog open={leaveTo !== null} onOpenChange={(open) => !open && stay()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Leave with unsaved changes?</AlertDialogTitle>
          <AlertDialogDescription>Your changes are not saved. Leaving drops them.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={stay}>Keep editing</AlertDialogCancel>
          <AlertDialogAction onClick={leave}>Leave without saving</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
