'use client';

import { Component, type ErrorInfo, type ReactNode } from 'react';

/** An error that passed through {@link ComponentStackBoundary}. */
export type ErrorWithComponentStack = Error & { componentStack?: string };

/**
 * Tags an error with React's component stack, then hands the SAME error on to the
 * next boundary up (`app/global-error.tsx`), which Next mounts without one.
 *
 * Why (CLIENT-ERROR-REPORT, crew pass on b51007ba): Safari's DOMException (the
 * SecurityError of blocked storage) carries no `stack`, so a crash report said "No
 * stack recorded" and nobody could tell which component threw. The component stack
 * names it.
 *
 * `componentDidCatch` runs only once this boundary has committed, so it renders
 * nothing for one pass, records the stack, and then rethrows on the next render.
 */
export class ComponentStackBoundary extends Component<
  { children: ReactNode },
  { error: ErrorWithComponentStack | null; rethrow: boolean }
> {
  state = { error: null as ErrorWithComponentStack | null, rethrow: false };

  static getDerivedStateFromError(error: unknown) {
    return { error: error as ErrorWithComponentStack, rethrow: false };
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    if (error && typeof error === 'object' && info?.componentStack) {
      try {
        (error as ErrorWithComponentStack).componentStack = info.componentStack;
      } catch {
        // a frozen error object: pass it on untagged
      }
    }
    this.setState({ rethrow: true });
  }

  render() {
    if (this.state.error) {
      if (this.state.rethrow) throw this.state.error;
      return null;
    }
    return this.props.children;
  }
}
