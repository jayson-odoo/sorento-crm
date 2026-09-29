/**
 * AC-EM030/031 - the shared preview iframe: desktop (600px) / mobile (375px)
 * toggle, sandboxed, fed by `srcDoc`.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EmailPreviewFrame } from './EmailPreviewFrame';

describe('EmailPreviewFrame', () => {
  it('renders the subject and a sandboxed iframe with the given html, desktop width 600 by default', () => {
    render(<EmailPreviewFrame subject="Reset your password" html="<p>hi</p>" />);

    expect(screen.getByText('Reset your password')).toBeInTheDocument();
    const iframe = screen.getByTitle('Email preview') as HTMLIFrameElement;
    expect(iframe).toHaveAttribute('sandbox', '');
    expect(iframe.getAttribute('width')).toBe('600');
  });

  it('the mobile toggle switches the iframe to width 375', async () => {
    render(<EmailPreviewFrame subject="Reset your password" html="<p>hi</p>" />);

    await userEvent.click(screen.getByRole('tab', { name: 'Mobile' }));

    const iframe = screen.getByTitle('Email preview') as HTMLIFrameElement;
    expect(iframe.getAttribute('width')).toBe('375');
  });
});
