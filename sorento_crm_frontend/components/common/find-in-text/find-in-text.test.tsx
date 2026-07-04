import { afterEach, describe, expect, it } from 'vitest';
import {
  act,
  cleanup,
  fireEvent,
  render,
  renderHook,
  screen,
} from '@testing-library/react';
import { FindBar, isFindChord } from './FindBar';
import { SearchableCode } from './SearchableCode';
import { SearchableTextarea } from './SearchableTextarea';
import { useFindController } from './useFindController';

// jsdom implements neither scrollIntoView nor a real scroll box; the source
// guards scrollIntoView with an optional chain, and setSelectionRange exists on
// jsdom's HTMLTextAreaElement (as a no-op). Stub scrollIntoView defensively so
// any un-guarded ref call cannot TypeError.
if (!(HTMLElement.prototype as unknown as { scrollIntoView?: unknown }).scrollIntoView) {
  (HTMLElement.prototype as unknown as { scrollIntoView: () => void }).scrollIntoView = () => {};
}

// "tool tool tool other" (lower-cased) -> 3 non-overlapping "tool" matches at 0,5,10.
const SAMPLE = 'tool Tool TOOL other';

afterEach(() => cleanup());

describe('useFindController', () => {
  it('reports 0 matches and activeIndex -1 for an empty query', () => {
    const { result } = renderHook(() => useFindController(SAMPLE));
    expect(result.current.query).toBe('');
    expect(result.current.matches).toHaveLength(0);
    expect(result.current.activeIndex).toBe(-1);
  });

  it('finds all case-insensitive occurrences and starts at index 0', () => {
    const { result } = renderHook(() => useFindController(SAMPLE));
    act(() => result.current.setQuery('tool'));
    expect(result.current.matches).toHaveLength(3);
    expect(result.current.matches[0]).toEqual({ start: 0, end: 4 });
    expect(result.current.matches[1]).toEqual({ start: 5, end: 9 });
    expect(result.current.matches[2]).toEqual({ start: 10, end: 14 });
    expect(result.current.activeIndex).toBe(0);
  });

  it('next() wraps 0 -> 1 -> 2 -> 0', () => {
    const { result } = renderHook(() => useFindController(SAMPLE));
    act(() => result.current.setQuery('tool'));
    act(() => result.current.next());
    expect(result.current.activeIndex).toBe(1);
    act(() => result.current.next());
    expect(result.current.activeIndex).toBe(2);
    act(() => result.current.next());
    expect(result.current.activeIndex).toBe(0);
  });

  it('prev() wraps 0 -> 2', () => {
    const { result } = renderHook(() => useFindController(SAMPLE));
    act(() => result.current.setQuery('tool'));
    act(() => result.current.prev());
    expect(result.current.activeIndex).toBe(2);
  });

  it('setQuery resets the active index to 0', () => {
    const { result } = renderHook(() => useFindController(SAMPLE));
    act(() => result.current.setQuery('tool'));
    act(() => result.current.next()); // -> 1
    expect(result.current.activeIndex).toBe(1);
    act(() => result.current.setQuery('tool'));
    expect(result.current.activeIndex).toBe(0);
  });

  it('close clears the query and resets state', () => {
    const { result } = renderHook(() => useFindController(SAMPLE));
    act(() => result.current.openFind());
    act(() => result.current.setQuery('tool'));
    expect(result.current.open).toBe(true);
    act(() => result.current.close());
    expect(result.current.open).toBe(false);
    expect(result.current.query).toBe('');
    expect(result.current.matches).toHaveLength(0);
    expect(result.current.activeIndex).toBe(-1);
  });
});

/**
 * Small harness so the FindBar tests drive the real controller through its
 * public surface (open + query) rather than hand-mocking every handler.
 */
function BarHarness({ text }: { text: string }) {
  const controller = useFindController(text);
  return (
    <div>
      <button data-testid="do-open" onClick={controller.openFind}>
        open
      </button>
      <button data-testid="do-setq" onClick={() => controller.setQuery('tool')}>
        set query
      </button>
      <FindBar controller={controller} />
    </div>
  );
}

describe('FindBar', () => {
  it('renders nothing while the controller is closed', () => {
    render(<BarHarness text={SAMPLE} />);
    expect(screen.queryByTestId('find-bar')).not.toBeInTheDocument();
  });

  it('shows "0/0" for an empty query once opened', () => {
    render(<BarHarness text={SAMPLE} />);
    fireEvent.click(screen.getByTestId('do-open'));
    expect(screen.getByTestId('find-bar')).toBeInTheDocument();
    expect(screen.getByTestId('find-count')).toHaveTextContent('0/0');
  });

  it('shows "1/3" at the first of three matches', () => {
    render(<BarHarness text={SAMPLE} />);
    fireEvent.click(screen.getByTestId('do-open'));
    fireEvent.click(screen.getByTestId('do-setq'));
    expect(screen.getByTestId('find-count')).toHaveTextContent('1/3');
  });

  it('advances the active match to "2/3" when find-next is clicked', () => {
    render(<BarHarness text={SAMPLE} />);
    fireEvent.click(screen.getByTestId('do-open'));
    fireEvent.click(screen.getByTestId('do-setq'));
    fireEvent.click(screen.getByTestId('find-next'));
    expect(screen.getByTestId('find-count')).toHaveTextContent('2/3');
  });

  it('typing in find-input updates the match count', () => {
    render(<BarHarness text={SAMPLE} />);
    fireEvent.click(screen.getByTestId('do-open'));
    fireEvent.change(screen.getByTestId('find-input'), { target: { value: 'tool' } });
    expect(screen.getByTestId('find-count')).toHaveTextContent('1/3');
  });

  it('Enter advances (next) and Shift+Enter goes back (prev)', () => {
    render(<BarHarness text={SAMPLE} />);
    fireEvent.click(screen.getByTestId('do-open'));
    fireEvent.change(screen.getByTestId('find-input'), { target: { value: 'tool' } });
    const input = screen.getByTestId('find-input');
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(screen.getByTestId('find-count')).toHaveTextContent('2/3');
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });
    expect(screen.getByTestId('find-count')).toHaveTextContent('1/3');
  });

  it('Escape on the input closes the bar', () => {
    render(<BarHarness text={SAMPLE} />);
    fireEvent.click(screen.getByTestId('do-open'));
    fireEvent.keyDown(screen.getByTestId('find-input'), { key: 'Escape' });
    expect(screen.queryByTestId('find-bar')).not.toBeInTheDocument();
  });

  it('the close button hides the bar', () => {
    render(<BarHarness text={SAMPLE} />);
    fireEvent.click(screen.getByTestId('do-open'));
    expect(screen.getByTestId('find-bar')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('find-close'));
    expect(screen.queryByTestId('find-bar')).not.toBeInTheDocument();
  });
});

describe('SearchableCode', () => {
  it('renders the text and no marks with no query', () => {
    render(<SearchableCode text={SAMPLE} data-testid="code" />);
    const panel = screen.getByTestId('code');
    expect(panel).toHaveTextContent('tool Tool TOOL other');
    expect(panel).toHaveAttribute('role', 'textbox');
    expect(panel).toHaveAttribute('aria-readonly', 'true');
    expect(panel.querySelectorAll('mark')).toHaveLength(0);
  });

  it('opens the find bar via the Cmd/Ctrl+F chord', () => {
    render(<SearchableCode text={SAMPLE} data-testid="code" />);
    expect(screen.queryByTestId('find-bar')).not.toBeInTheDocument();
    fireEvent.keyDown(screen.getByTestId('code'), { key: 'f', metaKey: true });
    expect(screen.getByTestId('find-bar')).toBeInTheDocument();
  });

  it('highlights matches as <mark>, the active one carrying bg-primary', () => {
    render(<SearchableCode text={SAMPLE} data-testid="code" />);
    fireEvent.keyDown(screen.getByTestId('code'), { key: 'f', metaKey: true });
    fireEvent.change(screen.getByTestId('find-input'), { target: { value: 'tool' } });

    const marks = screen.getByTestId('code').querySelectorAll('mark');
    expect(marks).toHaveLength(3);
    // active match is index 0
    expect(marks[0].className).toContain('bg-primary');
    expect(marks[1].className).not.toContain('bg-primary');
    expect(screen.getByTestId('find-count')).toHaveTextContent('1/3');
  });

  it('moves the active bg-primary mark when advancing to the next match', () => {
    render(<SearchableCode text={SAMPLE} data-testid="code" />);
    fireEvent.keyDown(screen.getByTestId('code'), { key: 'f', metaKey: true });
    fireEvent.change(screen.getByTestId('find-input'), { target: { value: 'tool' } });
    fireEvent.click(screen.getByTestId('find-next'));

    const marks = screen.getByTestId('code').querySelectorAll('mark');
    expect(marks[0].className).not.toContain('bg-primary');
    expect(marks[1].className).toContain('bg-primary');
    expect(screen.getByTestId('find-count')).toHaveTextContent('2/3');
  });
});

describe('SearchableTextarea', () => {
  it('opens its find bar via Cmd/Ctrl+F and reflects the match count', () => {
    render(<SearchableTextarea value={SAMPLE} readOnly data-testid="ta" />);
    expect(screen.queryByTestId('find-bar')).not.toBeInTheDocument();

    // fire the chord on the wrapping container (bubbles from the textarea).
    fireEvent.keyDown(screen.getByTestId('ta'), { key: 'f', ctrlKey: true });
    expect(screen.getByTestId('find-bar')).toBeInTheDocument();

    fireEvent.change(screen.getByTestId('find-input'), { target: { value: 'tool' } });
    expect(screen.getByTestId('find-count')).toHaveTextContent('1/3');
  });
});

describe('isFindChord', () => {
  it('is true for Cmd+F and Ctrl+F (either case of f)', () => {
    expect(isFindChord({ key: 'f', metaKey: true, ctrlKey: false })).toBe(true);
    expect(isFindChord({ key: 'f', metaKey: false, ctrlKey: true })).toBe(true);
    expect(isFindChord({ key: 'F', metaKey: true, ctrlKey: false })).toBe(true);
  });

  it('is false without the modifier or for another key', () => {
    expect(isFindChord({ key: 'f', metaKey: false, ctrlKey: false })).toBe(false);
    expect(isFindChord({ key: 'g', metaKey: true, ctrlKey: false })).toBe(false);
    expect(isFindChord({ key: 'a', metaKey: false, ctrlKey: true })).toBe(false);
  });
});
