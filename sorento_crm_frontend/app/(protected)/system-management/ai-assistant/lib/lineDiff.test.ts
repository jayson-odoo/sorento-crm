import { describe, expect, it } from 'vitest';
import { diffStats, lineDiff } from './lineDiff';

describe('lineDiff', () => {
  it('marks identical text as all-equal', () => {
    const rows = lineDiff('a\nb\nc', 'a\nb\nc');
    expect(rows.every((r) => r.op === 'equal')).toBe(true);
    expect(diffStats(rows)).toEqual({ added: 0, removed: 0 });
  });

  it('detects an appended line as added', () => {
    const rows = lineDiff('a\nb', 'a\nb\nc');
    const added = rows.filter((r) => r.op === 'added');
    expect(added).toHaveLength(1);
    expect(added[0].text).toBe('c');
    expect(diffStats(rows)).toEqual({ added: 1, removed: 0 });
  });

  it('detects a removed line', () => {
    const rows = lineDiff('a\nb\nc', 'a\nc');
    const removed = rows.filter((r) => r.op === 'removed');
    expect(removed).toHaveLength(1);
    expect(removed[0].text).toBe('b');
    expect(diffStats(rows)).toEqual({ added: 0, removed: 1 });
  });

  it('handles a replacement as removed + added', () => {
    const rows = lineDiff('hello world', 'hello there');
    const stats = diffStats(rows);
    expect(stats.added).toBe(1);
    expect(stats.removed).toBe(1);
  });

  it('assigns 1-based line numbers', () => {
    const rows = lineDiff('x\ny', 'x\ny');
    expect(rows[0].aLine).toBe(1);
    expect(rows[1].bLine).toBe(2);
  });
});
