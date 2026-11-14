/**
 * SAMPLE-REQUEST-V2, owner hand test 12 Nov ~15:45 (F2): the project reads the same on the portal
 * (the "user form") as on the CRM form. With a registered project picked, the project is that one
 * line ("code - title") and there is no second, typed "Project Title" holding the title again;
 * without one, the typed title is the field (the CRM form's rule: SampleRequestForm.tsx, staff).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/toast', () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() } }));
vi.mock('@/components/common/AttachmentPreviewModal', () => ({ __esModule: true, default: () => null }));

import SampleRequestForm from './SampleRequestForm';

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify([]), { status: 200, headers: { 'content-type': 'application/json' } })),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe('portal sample request: the project field matches the CRM form', () => {
  it('a registered project picked: no second Project Title field repeating the title', async () => {
    render(
      <SampleRequestForm
        initialValues={{ project_id: 'prj-1', project_label: 'PPF2611001 - Residensi Taman Seri Murni' }}
      />,
    );
    await screen.findByText(/Registered project/);
    expect(document.getElementById('sr-project-title')).toBeNull();
  });

  it('no registered project: the typed Project Title is the field', async () => {
    render(<SampleRequestForm />);
    await screen.findByText(/Registered project/);
    expect(document.getElementById('sr-project-title')).not.toBeNull();
  });
});

describe('crew pass round 3 (owner point 3): the portal project is one clamped line too', () => {
  const LABEL = 'PPF2611001 - Residensi Taman Seri Murni Fasa 2B, Blok A hingga D, Pembangunan Bercampur';
  it('a picked project reads as one clamped line with the whole label on hover, and can be cleared', async () => {
    render(<SampleRequestForm initialValues={{ project_id: 'prj-1', project_label: LABEL }} />);
    await screen.findByText(/Registered project/);
    const label = await screen.findByTitle(LABEL);
    expect(label.className).toMatch(/(^|\s)truncate(\s|$)/);
    fireEvent.click(screen.getByRole('button', { name: 'Clear project' }));
    expect(screen.queryByTitle(LABEL)).toBeNull();
    expect(document.getElementById('sr-project-title')).not.toBeNull();
  });
});
