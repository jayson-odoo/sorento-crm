/**
 * CertificateRevisionTimeline - the delivery-tracking revision history.
 *   FE-6 (newest-first reading order, one node per event, rail-and-dot markup:
 *     `ol.relative` with the `before:` rail and `li.relative` nodes; the current
 *     revision's dot is primary, superseded dots are muted)
 *   FE-6a (each node carries what happened - Issued / Renewed - plus the
 *     revision number, the validity window, the file with preview / download or
 *     the "File removed" state when the attachment was trashed, and that
 *     revision's access levels, so a renewal that widened visibility is visible
 *     rather than silent)
 *   REV-5 (a trashed attachment still renders its revision row with its dates,
 *     never a broken URL)
 *   empty state
 *
 * Pure presentational component: no hooks, no network, nothing to mock beyond
 * next/link, which jsdom renders as an anchor already.
 */
import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, cleanup, within } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

import CertificateRevisionTimeline from './CertificateRevisionTimeline';
import type { CertificateRevision } from '../types/certificate.types';

function revision(over: Partial<CertificateRevision> = {}): CertificateRevision {
  return {
    id: 'rev-1',
    revision_no: 1,
    issued_at: '2021-03-01',
    valid_from: '2021-03-01',
    valid_until: '2024-03-01',
    is_current: false,
    source: 'ai',
    needs_review: false,
    review_reasons: [],
    unmatched_products: [],
    access_levels: ['sorento_dealer'],
    attachment_filename: 'pps-2021.pdf',
    attachment_is_deleted: false,
    preview_url: 'https://cdn.example/pps-2021.pdf?sig=1',
    download_url: 'https://cdn.example/pps-2021.pdf?dl=1',
    created_at: '2021-03-02T02:00:00',
    ...over,
  };
}

const OLD = revision({ id: 'rev-1', revision_no: 1, is_current: false });
const CURRENT = revision({
  id: 'rev-2',
  revision_no: 2,
  is_current: true,
  valid_from: '2024-03-01',
  valid_until: '2027-03-01',
  attachment_filename: 'pps-2024.pdf',
  attachment_is_deleted: false,
  preview_url: 'https://cdn.example/pps-2024.pdf?sig=1',
  download_url: 'https://cdn.example/pps-2024.pdf?dl=1',
  created_at: '2024-03-02T02:00:00',
});

function renderTimeline(revisions: CertificateRevision[], currentAccessLevels: string[] = ['sorento_dealer']) {
  return render(
    <CertificateRevisionTimeline revisions={revisions} currentAccessLevels={currentAccessLevels} />,
  );
}

beforeEach(() => cleanup());

describe('CertificateRevisionTimeline - empty state', () => {
  it('renders the "no revision on file" state with an upload CTA', () => {
    renderTimeline([]);
    expect(screen.getByText('No revision on file')).toBeInTheDocument();
    expect(screen.getByText(/This certificate has no document behind it yet/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Upload the document/i })).toHaveAttribute(
      'href',
      '/resource-management/attachment-directories',
    );
  });
});

describe('CertificateRevisionTimeline - newest first (FE-6)', () => {
  it('orders nodes newest-first regardless of the input order', () => {
    // Deliberately handed oldest-first: the component must re-sort.
    const { container } = renderTimeline([OLD, CURRENT]);
    const nodes = Array.from(container.querySelectorAll('li'));
    expect(nodes).toHaveLength(2);
    expect(within(nodes[0] as HTMLElement).getByText('Revision 2')).toBeInTheDocument();
    expect(within(nodes[1] as HTMLElement).getByText('Revision 1')).toBeInTheDocument();
  });

  it('uses the shared rail-and-dot markup rather than a plain list', () => {
    const { container } = renderTimeline([CURRENT]);
    const list = container.querySelector('ol');
    expect(list?.className).toContain('relative');
    expect(list?.className).toContain('before:absolute');
    expect(container.querySelector('li')?.className).toContain('relative');
  });

  it('labels revision 1 "Issued" and later revisions "Renewed"', () => {
    renderTimeline([OLD, CURRENT]);
    expect(screen.getByText('Issued')).toBeInTheDocument();
    expect(screen.getByText('Renewed')).toBeInTheDocument();
  });
});

describe('CertificateRevisionTimeline - current vs superseded styling (FE-6)', () => {
  it('gives the current node a primary dot and the superseded node a muted dot', () => {
    const { container } = renderTimeline([OLD, CURRENT]);
    const nodes = Array.from(container.querySelectorAll('li'));
    const dotOf = (li: Element) => (li.querySelector('span[aria-hidden]') as HTMLElement).className;
    // Newest first, so node 0 is the current revision.
    expect(dotOf(nodes[0])).toContain('bg-primary');
    expect(dotOf(nodes[0])).not.toContain('bg-muted-foreground/40');
    expect(dotOf(nodes[1])).toContain('bg-muted-foreground/40');
    expect(dotOf(nodes[1])).not.toContain('bg-primary');
  });

  it('badges the current revision "Current" and the older one "Superseded"', () => {
    const { container } = renderTimeline([OLD, CURRENT]);
    const nodes = Array.from(container.querySelectorAll('li'));
    expect(within(nodes[0] as HTMLElement).getByText('Current')).toBeInTheDocument();
    expect(within(nodes[1] as HTMLElement).getByText('Superseded')).toBeInTheDocument();
  });
});

describe('CertificateRevisionTimeline - node contents (FE-6a)', () => {
  it('shows the validity window and both absolute and relative time', () => {
    // No "filed by" assertion: CertificateRevisionResponse carries `created_by`
    // as a bare user id and no resolved name, and the UI must not render an id.
    const { container } = renderTimeline([CURRENT]);
    const node = container.querySelector('li') as HTMLElement;
    expect(within(node).getByText(/ to /)).toBeInTheDocument();
    // Relative + absolute stamps both render (timeAgo + formatDateTime).
    expect(node.querySelectorAll('.text-xs').length).toBeGreaterThanOrEqual(2);
  });

  it('renders the file with working preview and download links', () => {
    renderTimeline([CURRENT]);
    expect(screen.getByText('pps-2024.pdf')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Preview/i })).toHaveAttribute(
      'href',
      'https://cdn.example/pps-2024.pdf?sig=1',
    );
    expect(screen.getByRole('link', { name: /Download/i })).toHaveAttribute(
      'href',
      'https://cdn.example/pps-2024.pdf?dl=1',
    );
  });

  it('renders the access levels of that revision', () => {
    renderTimeline([revision({ is_current: true, access_levels: ['sorento_dealer', 'cabana_office'] })], [
      'sorento_dealer',
      'cabana_office',
    ]);
    expect(screen.getByText('Sorento Dealer')).toBeInTheDocument();
    expect(screen.getByText('Cabana Office')).toBeInTheDocument();
  });

  it('says so when a revision has no access level recorded', () => {
    renderTimeline([revision({ is_current: true, access_levels: [] })], []);
    expect(screen.getByText('No access level recorded')).toBeInTheDocument();
  });

  it('says so when a revision has no file at all', () => {
    renderTimeline([revision({ is_current: true, attachment_filename: null, attachment_is_deleted: null })]);
    expect(screen.getByText('No file attached to this revision.')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Preview/i })).not.toBeInTheDocument();
  });
});

describe('CertificateRevisionTimeline - trashed attachment (REV-5)', () => {
  it('renders the "File removed" state with the filename and no broken link', () => {
    renderTimeline([
      revision({
        is_current: true,
        attachment_filename: 'pps-2021.pdf',
        attachment_is_deleted: true,
        preview_url: null,
        download_url: null,
      }),
    ]);
    expect(screen.getByText('File removed')).toBeInTheDocument();
    expect(screen.getByText('pps-2021.pdf')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Preview/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Download/i })).not.toBeInTheDocument();
  });

  it('still renders the revision row with its dates when the file is gone', () => {
    renderTimeline([
      revision({
        revision_no: 2,
        is_current: true,
        valid_from: '2024-03-01',
        valid_until: '2027-03-01',
        attachment_filename: 'gone.pdf',
        attachment_is_deleted: true,
        preview_url: null,
        download_url: null,
      }),
    ]);
    expect(screen.getByText('Revision 2')).toBeInTheDocument();
    expect(screen.getByText(/ to /)).toBeInTheDocument();
  });
});

describe('CertificateRevisionTimeline - access levels differ note (FE-6a)', () => {
  it('flags a superseded revision whose visibility does not match the current one', () => {
    const { container } = renderTimeline(
      [
        revision({ id: 'rev-1', revision_no: 1, is_current: false, access_levels: ['sorento_dealer'] }),
        revision({
          id: 'rev-2',
          revision_no: 2,
          is_current: true,
          access_levels: ['sorento_dealer', 'cabana_office'],
        }),
      ],
      ['sorento_dealer', 'cabana_office'],
    );
    const nodes = Array.from(container.querySelectorAll('li'));
    // Only the superseded node carries the note; the current one never does.
    expect(within(nodes[1] as HTMLElement).getByText('Visibility changed at the current revision.')).toBeInTheDocument();
    expect(within(nodes[0] as HTMLElement).queryByText('Visibility changed at the current revision.')).toBeNull();
  });

  it('stays silent when the superseded revision has the same access levels', () => {
    renderTimeline(
      [
        revision({ id: 'rev-1', revision_no: 1, is_current: false, access_levels: ['sorento_dealer'] }),
        revision({ id: 'rev-2', revision_no: 2, is_current: true, access_levels: ['sorento_dealer'] }),
      ],
      ['sorento_dealer'],
    );
    expect(screen.queryByText('Visibility changed at the current revision.')).toBeNull();
  });

  it('flags a same-length but differently-scoped superseded revision', () => {
    renderTimeline(
      [
        revision({ id: 'rev-1', revision_no: 1, is_current: false, access_levels: ['cabana_office'] }),
        revision({ id: 'rev-2', revision_no: 2, is_current: true, access_levels: ['sorento_dealer'] }),
      ],
      ['sorento_dealer'],
    );
    expect(screen.getByText('Visibility changed at the current revision.')).toBeInTheDocument();
  });
});
