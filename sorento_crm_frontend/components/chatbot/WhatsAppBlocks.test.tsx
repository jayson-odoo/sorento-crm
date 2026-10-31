/**
 * AGENTIC-UNIFY PR 3, slice 4 (red): `WhatsAppBlocks`, a reply drawn as text and real lists (AC-21).
 *
 * Contract: `<WhatsAppBlocks text={...} />` parses with `parseWhatsAppBlocks`, draws a list block as a real
 * `ul`/`ol` with `li` items (the `ol` carries `start`, the list a hanging indent) and everything inline
 * through `WhatsAppText`. `WhatsAppText` itself is untouched (AC-25).
 * Assumed: the hanging indent is a Tailwind start padding class (`ps-N` or `pl-N`) on the list, with
 * `list-disc` / `list-decimal` so the marker draws.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WhatsAppBlocks } from './WhatsAppBlocks';

describe('WhatsAppBlocks', () => {
  it('draws an unordered list as real ul and li elements with a hanging indent', () => {
    const { container } = render(<WhatsAppBlocks text={'Stock:\n- Alpha\n- Beta'} />);
    const ul = container.querySelector('ul');
    expect(ul).not.toBeNull();
    expect(container.querySelector('ol')).toBeNull();
    const items = screen.getAllByRole('listitem');
    expect(items.map((li) => li.textContent)).toEqual(['Alpha', 'Beta']);
    expect(ul!.className).toMatch(/(^|\s)(ps|pl)-\d/);
    expect(ul!.className).toContain('list-disc');
    expect(screen.getByText('Stock:')).toBeDefined();
  });

  it('draws numbering as an ol that carries its start', () => {
    const { container } = render(<WhatsAppBlocks text={'3. c\n4. d'} />);
    const ol = container.querySelector('ol');
    expect(ol).not.toBeNull();
    expect(ol!.getAttribute('start')).toBe('3');
    expect(ol!.className).toContain('list-decimal');
    expect(screen.getAllByRole('listitem').map((li) => li.textContent)).toEqual(['c', 'd']);
  });

  it('turns bold and italic into strong and em with no raw marker on screen', () => {
    const { container } = render(<WhatsAppBlocks text={'*Total* is _low_\n- *Alpha* here\n- _Beta_ there'} />);
    expect(container.querySelectorAll('strong').length).toBe(2);
    expect(container.querySelectorAll('em').length).toBe(2);
    expect(container.textContent).not.toContain('*');
    expect(container.textContent).not.toContain('_');
    const first = screen.getAllByRole('listitem')[0];
    expect(first.querySelector('strong')?.textContent).toBe('Alpha');
  });

  it('makes a bare URL a link, inside an item too', () => {
    render(<WhatsAppBlocks text={'See https://example.invalid/a\n- https://example.invalid/b'} />);
    const hrefs = screen.getAllByRole('link').map((a) => a.getAttribute('href'));
    expect(hrefs).toEqual(['https://example.invalid/a', 'https://example.invalid/b']);
  });

  it('keeps line breaks of a text block', () => {
    const { container } = render(<WhatsAppBlocks text={'line one\nline two'} />);
    const block = container.firstElementChild as HTMLElement;
    expect(block.textContent).toBe('line one\nline two');
    expect(`${block.className} ${block.innerHTML}`).toMatch(/whitespace-pre-(wrap|line)/);
  });

  it('keeps literal HTML in a reply as text', () => {
    const { container } = render(<WhatsAppBlocks text={'<b>not bold</b> <script>alert(1)</script>\n- <img src=x>'} />);
    expect(container.querySelector('b')).toBeNull();
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toContain('<b>not bold</b>');
    expect(container.textContent).toContain('<img src=x>');
  });

  it('renders nothing for an empty reply', () => {
    const { container } = render(<WhatsAppBlocks text="" />);
    expect(container.textContent).toBe('');
    expect(container.querySelector('ul,ol')).toBeNull();
  });
});
