/**
 * CLIENT-ERROR-REPORT, crew pass on b51007ba: Safari's SecurityError (a DOMException)
 * has no stack, so its crash row said "No stack recorded". The boundary tags the error
 * with React's component stack and passes the same error on to global-error.
 */
import React, { Component, type ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { ComponentStackBoundary, type ErrorWithComponentStack } from './ComponentStackBoundary';
import { buildClientErrorReport } from '@/lib/client-error-report';

class Outer extends Component<{ children: ReactNode }, { error: ErrorWithComponentStack | null }> {
  state = { error: null as ErrorWithComponentStack | null };
  static getDerivedStateFromError(error: ErrorWithComponentStack) {
    return { error };
  }
  render() {
    return this.state.error ? <p>outer caught</p> : this.props.children;
  }
}

const thrown = new DOMException('The operation is insecure.', 'SecurityError') as unknown as ErrorWithComponentStack;

function ImpersonationBannerLike(): ReactNode {
  throw thrown;
}

describe('ComponentStackBoundary', () => {
  it('passes the same error on, tagged with the component that threw', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    render(
      <Outer>
        <ComponentStackBoundary>
          <ImpersonationBannerLike />
        </ComponentStackBoundary>
      </Outer>,
    );
    expect(await screen.findByText('outer caught')).toBeTruthy();
    expect(thrown.componentStack).toContain('ImpersonationBannerLike');
  });

  it('renders children when nothing throws', () => {
    render(
      <ComponentStackBoundary>
        <p>fine</p>
      </ComponentStackBoundary>,
    );
    expect(screen.getByText('fine')).toBeTruthy();
  });
});

describe('crash report stack', () => {
  it('a stackless error reports its component stack', () => {
    const e = { name: 'SecurityError', message: 'The operation is insecure.', componentStack: '\n    at ImpersonationBanner' } as unknown as Error;
    expect(buildClientErrorReport(e, 'global').stack).toContain('ImpersonationBanner');
  });

  it('keeps the JS stack first when both exist', () => {
    const e = Object.assign(new Error('boom'), { componentStack: '\n    at Shell' });
    const stack = buildClientErrorReport(e, 'global').stack!;
    expect(stack.indexOf('Error: boom')).toBeLessThan(stack.indexOf('Component stack:'));
  });
});
