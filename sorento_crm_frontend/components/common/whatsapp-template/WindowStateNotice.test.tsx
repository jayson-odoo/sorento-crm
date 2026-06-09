import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import WindowStateNotice from './WindowStateNotice';

describe('WindowStateNotice', () => {
  it('renders nothing when the window is open', () => {
    const { container } = render(
      <WindowStateNotice
        windowState={{ open: true, last_incoming_at: null, checked_at: '2026-06-08T00:00:00Z' }}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('warns and shows last reply time when the window is closed', () => {
    render(
      <WindowStateNotice
        windowState={{
          open: false,
          last_incoming_at: '2026-06-06T10:00:00Z',
          checked_at: '2026-06-08T00:00:00Z',
        }}
      />,
    );
    expect(screen.getByTestId('window-closed-notice')).toBeInTheDocument();
    expect(screen.getByText(/24-hour window closed/i)).toBeInTheDocument();
    expect(screen.getByText(/Last reply from contact/i)).toBeInTheDocument();
  });

  it('omits the last-reply line when there is no incoming timestamp', () => {
    render(
      <WindowStateNotice
        windowState={{ open: false, last_incoming_at: null, checked_at: '2026-06-08T00:00:00Z' }}
      />,
    );
    expect(screen.getByTestId('window-closed-notice')).toBeInTheDocument();
    expect(screen.queryByText(/Last reply from contact/i)).not.toBeInTheDocument();
  });
});
