'use client';

import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { reportClientError } from '@/lib/client-error-report';
import { putUiVersion } from './uiVersionService';

interface State {
  error: Error | null;
  switching: boolean;
}

/**
 * Catches a crash inside a v2 screen (B-11): plain words plus the way back to v1 on the same URL.
 * It calls the API itself rather than through UiVersionProvider, which may be what broke.
 */
export class V2ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null, switching: false };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    void reportClientError(Object.assign(error, { componentStack: info.componentStack ?? undefined }), 'protected', {
      ui_version: 'v2',
    });
  }

  private openPrevious = async () => {
    this.setState({ switching: true });
    const ok = await putUiVersion('v1');
    // Never reload on a failed switch: the same broken screen would come straight back.
    if (ok) window.location.reload();
    else this.setState({ switching: false });
  };

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="mx-auto flex max-w-md flex-col items-center gap-4 px-4 py-16 text-center">
        <p className="text-base font-medium text-foreground">This screen hit a problem.</p>
        <Button onClick={() => void this.openPrevious()} disabled={this.state.switching}>
          Open in the previous version
        </Button>
      </div>
    );
  }
}
