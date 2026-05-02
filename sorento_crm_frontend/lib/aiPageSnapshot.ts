export interface AIPageSnapshot {
  path: string;
  search: string;
  title: string;
  visible_text: string;
}

export function getPageSnapshot(): AIPageSnapshot | null {
  if (typeof window === 'undefined') return null;
  // Selector priority: [data-ai-context] > main > body
  const root =
    document.querySelector<HTMLElement>('[data-ai-context]') ??
    document.querySelector<HTMLElement>('main') ??
    document.body;
  if (!root) return null;
  // Strip excluded subtrees first (data-ai-context-exclude) by cloning + removing
  const clone = root.cloneNode(true) as HTMLElement;
  clone.querySelectorAll('[data-ai-context-exclude]').forEach((n) => n.remove());
  // innerText respects visibility better than textContent
  const raw = (clone.innerText || '').replace(/\s+/g, ' ').trim();
  const visible_text = raw.slice(0, 6000);
  return {
    path: window.location.pathname,
    search: window.location.search,
    title: document.title,
    visible_text,
  };
}
