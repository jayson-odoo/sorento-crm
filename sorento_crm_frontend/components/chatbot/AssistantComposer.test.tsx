/**
 * AGENT-PANEL-COMPOSER: the panel's composer (UAC F1 to F6, F8, F9).
 *
 * `@/lib/aiAssistantChatApi` is mocked at the module boundary, so no network and no backend. The
 * Phase 1 component already exists, so these tests pin its behaviour for Phase 3 wiring rather than
 * fail first. The drop overlay (F3) lives on the panel, not here, and is covered by the panel's own
 * browser pass.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';

vi.mock('@/lib/aiAssistantChatApi', () => ({
  uploadAssistantFile: vi.fn(),
  deleteAssistantFile: vi.fn(),
}));
vi.mock('@/lib/toast', () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() } }));

import AssistantComposer from './AssistantComposer';
import { deleteAssistantFile, uploadAssistantFile, type AssistantFile } from '@/lib/aiAssistantChatApi';
import { toast } from '@/lib/toast';

const upload = vi.mocked(uploadAssistantFile);
const remove = vi.mocked(deleteAssistantFile);

const MB = 1024 * 1024;

function file(name: string, type = 'text/csv', size?: number): File {
  const f = new File(['a,b\n1,2\n'], name, { type });
  if (size !== undefined) Object.defineProperty(f, 'size', { value: size });
  return f;
}

function uploaded(over: Partial<AssistantFile> = {}): AssistantFile {
  return {
    id: 'att-1',
    filename: 'people.csv',
    size: 8,
    mime_type: 'text/csv',
    kind: 'sheet',
    thumb_url: null,
    sheets: [{ name: 'people', rows: 3 }],
    pages: null,
    ...over,
  };
}

interface Opts {
  canAttach?: boolean;
  isSending?: boolean;
  initial?: string;
  onSend?: (p: { text: string; attachments: { id: string; sheet: string | null }[] }) => Promise<void> | void;
}

function Harness({ canAttach = true, isSending = false, initial = '', onSend = vi.fn() }: Opts) {
  const [value, setValue] = useState(initial);
  return (
    <AssistantComposer
      value={value}
      onChange={setValue}
      onSend={onSend}
      isSending={isSending}
      canAttach={canAttach}
    />
  );
}

const box = () => screen.getByLabelText('Message the assistant') as HTMLTextAreaElement;
const sendButton = () => screen.getByRole('button', { name: 'Send message' });
const fileInput = () => screen.getByTestId('assistant-file-input') as HTMLInputElement;
const attach = (...files: File[]) => fireEvent.change(fileInput(), { target: { files } });

function setPointer(coarse: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: coarse && query.includes('coarse'),
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    onchange: null,
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

beforeEach(() => {
  upload.mockReset();
  remove.mockReset();
  remove.mockResolvedValue(undefined);
  vi.mocked(toast.error).mockReset();
  setPointer(false);
  window.localStorage.clear();
  delete (window as unknown as Record<string, unknown>).SpeechRecognition;
  delete (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('F1 keys', () => {
  it('Enter sends the typed text', () => {
    const onSend = vi.fn();
    render(<Harness initial="hello" onSend={onSend} />);

    fireEvent.keyDown(box(), { key: 'Enter' });

    expect(onSend).toHaveBeenCalledWith({ text: 'hello', attachments: [] });
  });

  it('Shift+Enter does not send', () => {
    const onSend = vi.fn();
    render(<Harness initial="hello" onSend={onSend} />);

    fireEvent.keyDown(box(), { key: 'Enter', shiftKey: true });

    expect(onSend).not.toHaveBeenCalled();
  });

  it('Enter while an IME is composing does not send', () => {
    const onSend = vi.fn();
    render(<Harness initial="hello" onSend={onSend} />);

    fireEvent.keyDown(box(), { key: 'Enter', isComposing: true });
    fireEvent.keyDown(box(), { key: 'Enter', keyCode: 229 });

    expect(onSend).not.toHaveBeenCalled();
  });

  it('Enter on a coarse pointer does not send; the button does', () => {
    setPointer(true);
    const onSend = vi.fn();
    render(<Harness initial="hello" onSend={onSend} />);

    fireEvent.keyDown(box(), { key: 'Enter' });
    expect(onSend).not.toHaveBeenCalled();

    fireEvent.click(sendButton());
    expect(onSend).toHaveBeenCalledWith({ text: 'hello', attachments: [] });
  });

  it('an empty box cannot be sent', () => {
    const onSend = vi.fn();
    render(<Harness initial="   " onSend={onSend} />);

    fireEvent.keyDown(box(), { key: 'Enter' });

    expect(sendButton()).toBeDisabled();
    expect(onSend).not.toHaveBeenCalled();
  });

  it('while a message is sending, Enter and the button do nothing', () => {
    const onSend = vi.fn();
    render(<Harness initial="hello" isSending onSend={onSend} />);

    fireEvent.keyDown(box(), { key: 'Enter' });

    expect(onSend).not.toHaveBeenCalled();
  });
});

describe('F2 paste', () => {
  it('text plus an image on the clipboard pastes the text and adds no chip', () => {
    render(<Harness />);
    const image = new File(['x'], 'image.png', { type: 'image/png' });

    const notPrevented = fireEvent.paste(box(), {
      clipboardData: { getData: (t: string) => (t === 'text/plain' ? 'a\tb\n1\t2' : ''), files: [image] },
    });

    expect(notPrevented).toBe(true);
    expect(upload).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: /^Remove / })).toBeNull();
  });

  it('an image alone on the clipboard becomes an uploaded chip', async () => {
    upload.mockResolvedValue(uploaded({ id: 'img-1', filename: 'image.png', kind: 'image', sheets: [] }));
    render(<Harness />);
    const image = new File(['x'], 'image.png', { type: 'image/png' });

    fireEvent.paste(box(), { clipboardData: { getData: () => '', files: [image] } });

    await waitFor(() => expect(upload).toHaveBeenCalledWith(image));
    expect(await screen.findByRole('button', { name: 'Remove image.png' })).toBeInTheDocument();
  });

  it('a non-image file on the clipboard is ignored', () => {
    render(<Harness />);
    const doc = new File(['x'], 'a.pdf', { type: 'application/pdf' });

    fireEvent.paste(box(), { clipboardData: { getData: () => '', files: [doc] } });

    expect(upload).not.toHaveBeenCalled();
  });
});

describe('F3 client-side refusals', () => {
  it('refuses a type outside the list without uploading', () => {
    render(<Harness />);

    attach(file('notes.docx', 'application/msword'));

    expect(upload).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Remove notes.docx' })).toBeInTheDocument();
    expect(sendButton()).toBeDisabled();
  });

  it('refuses .xlsm with the macro message', () => {
    render(<Harness />);

    attach(file('macros.xlsm', 'application/vnd.ms-excel.sheet.macroEnabled.12'));

    expect(upload).not.toHaveBeenCalled();
    expect(screen.getByText(/Macro workbooks are not read; save as \.xlsx/)).toBeInTheDocument();
  });

  it('refuses a file over 10 MB', () => {
    render(<Harness />);

    attach(file('big.csv', 'text/csv', 11 * MB));

    expect(upload).not.toHaveBeenCalled();
    expect(screen.getByText(/10 MB/)).toBeInTheDocument();
  });

  it('refuses the sixth file with the count message and uploads only five', async () => {
    upload.mockImplementation(async (f: File) => uploaded({ id: `id-${f.name}`, filename: f.name }));
    render(<Harness />);

    attach(...['a', 'b', 'c', 'd', 'e', 'f'].map((n) => file(`${n}.csv`)));

    expect(screen.getByText('At most 5 files per message')).toBeInTheDocument();
    await waitFor(() => expect(upload).toHaveBeenCalledTimes(5));
  });

  it('accepts all eight extensions in the picker', () => {
    render(<Harness />);

    const accept = fileInput().getAttribute('accept') ?? '';

    for (const ext of ['.png', '.jpg', '.jpeg', '.webp', '.xlsx', '.xls', '.csv', '.pdf']) {
      expect(accept.split(',')).toContain(ext);
    }
    expect(accept).not.toContain('.xlsm');
    expect(fileInput().multiple).toBe(true);
  });
});

describe('F4 chips', () => {
  it('uploads at once and shows the name with an uploading indicator', async () => {
    let finish: (v: AssistantFile) => void = () => undefined;
    upload.mockReturnValue(new Promise<AssistantFile>((res) => (finish = res)));
    render(<Harness />);

    attach(file('people.csv'));

    expect(upload).toHaveBeenCalledTimes(1);
    expect(screen.getByText('people.csv')).toHaveAttribute('title', 'people.csv');
    expect(screen.getByRole('progressbar')).toBeInTheDocument();

    await act(async () => finish(uploaded()));
    expect(screen.queryByRole('progressbar')).toBeNull();
  });

  it('removing an uploaded chip deletes the draft on the server', async () => {
    upload.mockResolvedValue(uploaded({ id: 'att-9' }));
    render(<Harness />);
    attach(file('people.csv'));
    const x = await screen.findByRole('button', { name: 'Remove people.csv' });
    await waitFor(() => expect(screen.queryByRole('progressbar')).toBeNull());

    fireEvent.click(x);

    expect(remove).toHaveBeenCalledWith('att-9');
    expect(screen.queryByRole('button', { name: 'Remove people.csv' })).toBeNull();
  });

  it('removing a refused chip calls no delete', () => {
    render(<Harness />);
    attach(file('notes.docx', 'application/msword'));

    fireEvent.click(screen.getByRole('button', { name: 'Remove notes.docx' }));

    expect(remove).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Remove notes.docx' })).toBeNull();
  });

  it('a server error turns the chip red with the server message and blocks send', async () => {
    upload.mockRejectedValue(new Error('This file cannot be read.'));
    render(<Harness initial="hello" />);

    attach(file('people.csv'));

    expect(await screen.findByText('This file cannot be read.')).toBeInTheDocument();
    expect(sendButton()).toBeDisabled();
  });

  it('shows no UUID anywhere on a ready chip', async () => {
    upload.mockResolvedValue(uploaded({ id: '3f2b8c1e-5d44-4e0a-9a51-0b7e6c1d2f90' }));
    const { container } = render(<Harness />);
    attach(file('people.csv'));
    await screen.findByText('3 rows');

    expect(container.textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}/);
  });
});

describe('F5 sheet picker', () => {
  it('is absent for a single-sheet file, which shows its row count', async () => {
    upload.mockResolvedValue(uploaded({ sheets: [{ name: 'Dealers', rows: 12 }] }));
    render(<Harness />);

    attach(file('d.xlsx'));

    expect(await screen.findByText('12 rows')).toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: /^Sheet of / })).toBeNull();
  });

  it('is present for a multi-sheet file, defaulting to the first sheet', async () => {
    upload.mockResolvedValue(
      uploaded({
        id: 'att-2',
        filename: 'd.xlsx',
        sheets: [
          { name: 'Dealers', rows: 12 },
          { name: 'Archive', rows: 40 },
        ],
      }),
    );
    const onSend = vi.fn();
    render(<Harness initial="grant access" onSend={onSend} />);

    attach(file('d.xlsx'));

    expect(await screen.findByRole('combobox', { name: 'Sheet of d.xlsx' })).toBeInTheDocument();
    expect(screen.getByText('12 rows')).toBeInTheDocument();
    fireEvent.click(sendButton());
    expect(onSend).toHaveBeenCalledWith({ text: 'grant access', attachments: [{ id: 'att-2', sheet: 'Dealers' }] });
  });
});

describe('F6 send gating and payload', () => {
  it('is disabled while an upload is pending and enabled once it lands', async () => {
    let finish: (v: AssistantFile) => void = () => undefined;
    upload.mockReturnValue(new Promise<AssistantFile>((res) => (finish = res)));
    render(<Harness initial="hello" />);

    attach(file('people.csv'));
    expect(sendButton()).toBeDisabled();

    await act(async () => finish(uploaded()));
    expect(sendButton()).toBeEnabled();
  });

  it('a ready file alone, with no text, can be sent', async () => {
    upload.mockResolvedValue(uploaded({ id: 'att-3' }));
    const onSend = vi.fn();
    render(<Harness onSend={onSend} />);
    attach(file('people.csv'));
    await waitFor(() => expect(sendButton()).toBeEnabled());

    fireEvent.click(sendButton());

    expect(onSend).toHaveBeenCalledWith({ text: '', attachments: [{ id: 'att-3', sheet: 'people' }] });
  });

  it('an image has a null sheet in the payload', async () => {
    upload.mockResolvedValue(uploaded({ id: 'img-2', filename: 'shot.png', kind: 'image', sheets: [] }));
    const onSend = vi.fn();
    render(<Harness initial="what is this" onSend={onSend} />);
    attach(file('shot.png', 'image/png'));
    await waitFor(() => expect(sendButton()).toBeEnabled());

    fireEvent.click(sendButton());

    expect(onSend).toHaveBeenCalledWith({ text: 'what is this', attachments: [{ id: 'img-2', sheet: null }] });
  });

  it('clears its chips after onSend resolves', async () => {
    upload.mockResolvedValue(uploaded());
    const onSend = vi.fn().mockResolvedValue(undefined);
    render(<Harness initial="hello" onSend={onSend} />);
    attach(file('people.csv'));
    await waitFor(() => expect(sendButton()).toBeEnabled());

    fireEvent.click(sendButton());

    await waitFor(() => expect(screen.queryByRole('button', { name: 'Remove people.csv' })).toBeNull());
  });

  it('keeps its chips when onSend fails, so the user can retry', async () => {
    upload.mockResolvedValue(uploaded());
    const onSend = vi.fn().mockRejectedValue(new Error('boom'));
    render(<Harness initial="hello" onSend={onSend} />);
    attach(file('people.csv'));
    await waitFor(() => expect(sendButton()).toBeEnabled());

    fireEvent.click(sendButton());

    await waitFor(() => expect(onSend).toHaveBeenCalled());
    expect(screen.getByRole('button', { name: 'Remove people.csv' })).toBeInTheDocument();
  });
});

describe('F8 canAttach false', () => {
  it('hides the paperclip and the file input', () => {
    render(<Harness canAttach={false} />);

    expect(screen.queryByRole('button', { name: 'Attach files' })).toBeNull();
    expect(screen.queryByTestId('assistant-file-input')).toBeNull();
  });

  it('ignores a pasted image', () => {
    render(<Harness canAttach={false} />);
    const image = new File(['x'], 'image.png', { type: 'image/png' });

    fireEvent.paste(box(), { clipboardData: { getData: () => '', files: [image] } });

    expect(upload).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: /^Remove / })).toBeNull();
  });

  it('still sends plain text', () => {
    const onSend = vi.fn();
    render(<Harness canAttach={false} initial="hi" onSend={onSend} />);

    fireEvent.keyDown(box(), { key: 'Enter' });

    expect(onSend).toHaveBeenCalledWith({ text: 'hi', attachments: [] });
  });
});

describe('F9 dictation', () => {
  class FakeRecognition {
    static instances: FakeRecognition[] = [];
    lang = '';
    continuous = false;
    interimResults = false;
    onresult: ((e: unknown) => void) | null = null;
    onerror: ((e: { error?: string }) => void) | null = null;
    onend: (() => void) | null = null;
    start = vi.fn();
    stop = vi.fn(() => this.onend?.());
    constructor() {
      FakeRecognition.instances.push(this);
    }
  }

  const install = (name: 'SpeechRecognition' | 'webkitSpeechRecognition' = 'webkitSpeechRecognition') => {
    FakeRecognition.instances = [];
    (window as unknown as Record<string, unknown>)[name] = FakeRecognition;
  };

  it('hides the mic when the browser has no speech engine', () => {
    render(<Harness />);

    expect(screen.queryByRole('button', { name: 'Dictate' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Dictation language' })).toBeNull();
  });

  it.each(['SpeechRecognition', 'webkitSpeechRecognition'] as const)('shows the mic with window.%s', (name) => {
    install(name);
    render(<Harness />);

    expect(screen.getByRole('button', { name: 'Dictate' })).toBeInTheDocument();
  });

  it('starts continuous with interim results in English, and stops on the second click', () => {
    install();
    render(<Harness />);

    fireEvent.click(screen.getByRole('button', { name: 'Dictate' }));
    const rec = FakeRecognition.instances[0];
    expect(rec.start).toHaveBeenCalled();
    expect(rec.continuous).toBe(true);
    expect(rec.interimResults).toBe(true);
    expect(rec.lang).toBe('en-US');

    fireEvent.click(screen.getByRole('button', { name: 'Stop dictation' }));
    expect(rec.stop).toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Dictate' })).toBeInTheDocument();
  });

  it('inserts final words into the text and sends nothing', () => {
    install();
    const onSend = vi.fn();
    render(<Harness initial="Hi" onSend={onSend} />);
    fireEvent.click(screen.getByRole('button', { name: 'Dictate' }));
    const rec = FakeRecognition.instances[0];

    act(() => {
      rec.onresult?.({
        resultIndex: 0,
        results: [{ isFinal: false, 0: { transcript: 'hel' } }],
      });
    });
    expect(box().value).toBe('Hi');

    act(() => {
      rec.onresult?.({
        resultIndex: 0,
        results: [{ isFinal: true, 0: { transcript: 'hello world' } }],
      });
    });

    expect(box().value).toBe('Hi hello world');
    expect(onSend).not.toHaveBeenCalled();
  });

  it('the language toggle switches to Bahasa Malaysia and is remembered', () => {
    install();
    const first = render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Dictation language' }));
    expect(screen.getByRole('button', { name: 'Dictation language' })).toHaveTextContent('BM');
    first.unmount();

    render(<Harness />);
    expect(screen.getByRole('button', { name: 'Dictation language' })).toHaveTextContent('BM');
    fireEvent.click(screen.getByRole('button', { name: 'Dictate' }));
    expect(FakeRecognition.instances.at(-1)?.lang).toBe('ms-MY');
  });

  it('a not-allowed error toasts the microphone message', () => {
    install();
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Dictate' }));

    act(() => {
      FakeRecognition.instances[0].onerror?.({ error: 'not-allowed' });
    });

    expect(toast.error).toHaveBeenCalledWith('Allow the microphone for this site');
  });

  it('stops by itself after 60 seconds with no result', () => {
    vi.useFakeTimers();
    install();
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Dictate' }));
    const rec = FakeRecognition.instances[0];

    act(() => {
      vi.advanceTimersByTime(59_000);
    });
    expect(rec.stop).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(1_500);
    });

    expect(rec.stop).toHaveBeenCalled();
  });
});

describe('F10 labels', () => {
  it('every icon button has an accessible name', () => {
    (window as unknown as Record<string, unknown>).webkitSpeechRecognition = class {
      start() {}
      stop() {}
    };
    render(<Harness />);

    for (const name of ['Attach files', 'Dictate', 'Dictation language', 'Send message']) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument();
    }
  });
});
