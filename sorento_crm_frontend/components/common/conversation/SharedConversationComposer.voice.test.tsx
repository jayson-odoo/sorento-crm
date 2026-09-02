/**
 * Voice messages in the chat composer (UAC AC-L9).
 *
 * Click to record, click to stop; the clip is staged as an ordinary attachment
 * so one send carries it. What is pinned here: the control only exists where a
 * message can reach the contact, the clip goes through the SAME staging path as
 * Attach and paste, the 2 minute cap stops it, and the microphone is released
 * on stop, on cancel and on unmount - a live mic left open is the failure that
 * matters.
 *
 * jsdom has neither `MediaRecorder` nor `getUserMedia`, so both are faked here.
 * That means the RECORDING ITSELF (real audio bytes, the container the browser
 * actually produces) is not exercised by this suite - it needs a browser.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import SharedConversationComposer from './SharedConversationComposer';
import InternalCommentComposer from './InternalCommentComposer';
import { voiceFileName, formatElapsed, pickVoiceMimeType } from './useVoiceRecorder';

vi.mock('@/services/whatsappTemplateService', async () => {
  const actual = await vi.importActual<typeof import('@/services/whatsappTemplateService')>(
    '@/services/whatsappTemplateService',
  );
  return {
    ...actual,
    getWindowState: vi.fn().mockResolvedValue({
      open: true,
      last_incoming_at: null,
      checked_at: '2026-08-16T00:00:00Z',
    }),
    sendConversationMessage: vi.fn(),
    getChatTemplatePreview: vi.fn(),
    listApprovedTemplates: vi.fn().mockResolvedValue([]),
    sendTemplateMessage: vi.fn(),
  };
});

const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: (...args: unknown[]) => toastError(...args) } }));

// ---- The fake browser recording stack ---------------------------------

interface FakeTrack {
  stop: ReturnType<typeof vi.fn>;
}

let tracks: FakeTrack[] = [];
let recorders: FakeRecorder[] = [];
let getUserMedia: ReturnType<typeof vi.fn>;

class FakeRecorder {
  static supported: string[] = ['audio/mp4', 'audio/ogg;codecs=opus', 'audio/webm;codecs=opus'];
  static isTypeSupported = (mime: string) => FakeRecorder.supported.includes(mime);
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  state = 'inactive';
  mimeType: string;
  constructor(
    public stream: unknown,
    options?: { mimeType?: string },
  ) {
    this.mimeType = options?.mimeType ?? '';
    recorders.push(this);
  }
  start() {
    this.state = 'recording';
  }
  stop() {
    this.state = 'inactive';
    // A real recorder flushes its last chunk, then fires onstop.
    this.ondataavailable?.({ data: new Blob(['audio-bytes'], { type: this.mimeType }) });
    this.onstop?.();
  }
}

function installRecordingStack({
  supported = ['audio/mp4', 'audio/ogg;codecs=opus', 'audio/webm;codecs=opus'],
  deny = false,
}: { supported?: string[]; deny?: boolean } = {}) {
  FakeRecorder.supported = supported;
  tracks = [];
  recorders = [];
  getUserMedia = vi.fn(async () => {
    if (deny) throw new Error('NotAllowedError');
    const track: FakeTrack = { stop: vi.fn() };
    tracks.push(track);
    return { getTracks: () => [track] } as unknown as MediaStream;
  });
  Object.defineProperty(globalThis, 'MediaRecorder', {
    configurable: true,
    writable: true,
    value: FakeRecorder,
  });
  Object.defineProperty(globalThis.navigator, 'mediaDevices', {
    configurable: true,
    writable: true,
    value: { getUserMedia },
  });
}

function uninstallRecordingStack() {
  Reflect.deleteProperty(globalThis as Record<string, unknown>, 'MediaRecorder');
  Object.defineProperty(globalThis.navigator, 'mediaDevices', {
    configurable: true,
    writable: true,
    value: undefined,
  });
}

beforeEach(() => {
  toastError.mockClear();
  Object.defineProperty(URL, 'createObjectURL', {
    configurable: true,
    writable: true,
    value: (file: File) => `blob:staged/${file.name}`,
  });
  Object.defineProperty(URL, 'revokeObjectURL', {
    configurable: true,
    writable: true,
    value: vi.fn(),
  });
  installRecordingStack();
});

afterEach(() => {
  vi.useRealTimers();
  uninstallRecordingStack();
});

function renderComposer(
  props: Partial<React.ComponentProps<typeof SharedConversationComposer>> = {},
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const sendAdapter = vi.fn().mockResolvedValue({
    sent_as: 'attachment',
    attachments: { delivered: ['clip'], failed: null },
  });
  const view = render(
    <QueryClientProvider client={qc}>
      <SharedConversationComposer
        entityType="conversation_sla"
        entityId="t1"
        canReply
        mode="conversation"
        attachmentsEnabled
        sendAdapter={sendAdapter}
        {...props}
      />
    </QueryClientProvider>,
  );
  return { ...view, sendAdapter };
}

/** Start recording and wait for the elapsed counter to appear. */
async function startRecording() {
  fireEvent.click(await screen.findByTestId('voice-record'));
  return screen.findByTestId('voice-recording');
}

describe('SharedConversationComposer - voice message (AC-L9)', () => {
  it('offers the mic in Reply mode', async () => {
    renderComposer();
    const button = await screen.findByTestId('voice-record');
    await waitFor(() => expect(button).toBeEnabled());
    expect(button).toHaveAccessibleName('Record voice message');
  });

  it('does NOT offer it on a surface that cannot send files to the contact', async () => {
    renderComposer({ attachmentsEnabled: false, sendAdapter: undefined });
    await screen.findByPlaceholderText('Type your message...');
    expect(screen.queryByTestId('voice-record')).not.toBeInTheDocument();
  });

  it('the internal note composer has no mic at all - a note cannot reach the contact', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <InternalCommentComposer onSubmit={vi.fn()} />
      </QueryClientProvider>,
    );
    expect(screen.queryByTestId('voice-record')).not.toBeInTheDocument();
  });

  it('start then stop stages the clip as an attachment, with playback', async () => {
    renderComposer();
    await startRecording();

    fireEvent.click(screen.getByTestId('voice-stop'));

    const staged = await screen.findByTestId('composer-attachment');
    expect(staged.getAttribute('title')).toMatch(/^voice-message-\d{8}-\d{6}\.m4a$/);
    expect(
      within(staged).getByTestId('composer-voice-playback').getAttribute('src'),
    ).toMatch(/^blob:staged\/voice-message-/);
    expect(screen.queryByTestId('voice-recording')).not.toBeInTheDocument();
  });

  it('sends the clip in the SAME send as the typed text', async () => {
    const { sendAdapter } = renderComposer();
    await startRecording();
    fireEvent.click(screen.getByTestId('voice-stop'));
    await screen.findByTestId('composer-attachment');

    fireEvent.change(screen.getByPlaceholderText('Type your message...'), {
      target: { value: 'listen to this' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }));

    await waitFor(() => expect(sendAdapter).toHaveBeenCalledTimes(1));
    const payload = sendAdapter.mock.calls[0][0] as { text: string; files: File[] };
    expect(payload.text).toBe('listen to this');
    expect(payload.files).toHaveLength(1);
    expect(payload.files[0].name).toMatch(/^voice-message-\d{8}-\d{6}\.m4a$/);
    expect(payload.files[0].type).toBe('audio/mp4');
  });

  it('cancel stages nothing and releases the microphone', async () => {
    renderComposer();
    await startRecording();

    fireEvent.click(screen.getByTestId('voice-cancel'));

    await waitFor(() =>
      expect(screen.queryByTestId('voice-recording')).not.toBeInTheDocument(),
    );
    expect(screen.queryByTestId('composer-attachment')).not.toBeInTheDocument();
    expect(tracks).toHaveLength(1);
    expect(tracks[0].stop).toHaveBeenCalled();
  });

  it('stopping normally also releases the microphone', async () => {
    renderComposer();
    await startRecording();

    fireEvent.click(screen.getByTestId('voice-stop'));

    await screen.findByTestId('composer-attachment');
    expect(tracks[0].stop).toHaveBeenCalled();
  });

  it('unmounting mid-recording releases the microphone and keeps no clip', async () => {
    const { unmount } = renderComposer();
    await startRecording();

    unmount();

    expect(tracks[0].stop).toHaveBeenCalled();
  });

  it('a second click during the permission prompt opens only one microphone', async () => {
    // The button still looks idle while the prompt is open, so clicking twice is
    // the ordinary user action; the second stream would be one nothing stops.
    const grants: (() => void)[] = [];
    const opened: FakeTrack[] = [];
    getUserMedia = vi.fn(
      () =>
        new Promise<MediaStream>((resolve) => {
          grants.push(() => {
            const track: FakeTrack = { stop: vi.fn() };
            opened.push(track);
            resolve({ getTracks: () => [track] } as unknown as MediaStream);
          });
        }),
    );
    Object.defineProperty(globalThis.navigator, 'mediaDevices', {
      configurable: true,
      writable: true,
      value: { getUserMedia },
    });

    renderComposer();
    const button = await screen.findByTestId('voice-record');
    fireEvent.click(button);
    fireEvent.click(button);
    await act(async () => {
      grants.forEach((grant) => grant());
    });

    expect(getUserMedia).toHaveBeenCalledTimes(1);
    expect(opened).toHaveLength(1);
  });

  it('releases a microphone granted AFTER the composer unmounted', async () => {
    // The permission prompt is open when the drawer closes: getUserMedia
    // resolves after cleanup has already run, so the stream it hands back is
    // one nothing else will ever stop.
    let grant: (() => void) | null = null;
    const track: FakeTrack = { stop: vi.fn() };
    getUserMedia = vi.fn(
      () =>
        new Promise<MediaStream>((resolve) => {
          grant = () => resolve({ getTracks: () => [track] } as unknown as MediaStream);
        }),
    );
    Object.defineProperty(globalThis.navigator, 'mediaDevices', {
      configurable: true,
      writable: true,
      value: { getUserMedia },
    });

    const { unmount } = renderComposer();
    fireEvent.click(await screen.findByTestId('voice-record'));
    unmount();
    await act(async () => {
      grant?.();
    });

    expect(track.stop).toHaveBeenCalled();
  });

  it('stops itself at the 2 minute cap and keeps what was recorded', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderComposer();
    fireEvent.click(await screen.findByTestId('voice-record'));
    await screen.findByTestId('voice-recording');

    await act(async () => {
      vi.advanceTimersByTime(120_000);
    });

    await waitFor(() =>
      expect(screen.queryByTestId('voice-recording')).not.toBeInTheDocument(),
    );
    expect(await screen.findByTestId('composer-attachment')).toBeInTheDocument();
    expect(tracks[0].stop).toHaveBeenCalled();
  });

  it('counts the elapsed seconds while recording', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderComposer();
    fireEvent.click(await screen.findByTestId('voice-record'));
    await screen.findByTestId('voice-recording');
    expect(screen.getByTestId('voice-elapsed')).toHaveTextContent('0:00');

    await act(async () => {
      vi.advanceTimersByTime(3000);
    });

    expect(screen.getByTestId('voice-elapsed')).toHaveTextContent('0:03');
  });

  it('is disabled when the browser cannot record', async () => {
    uninstallRecordingStack();
    renderComposer();

    const button = await screen.findByTestId('voice-record');
    await waitFor(() => expect(button).toBeDisabled());
    expect(button).toHaveAttribute('title', 'Voice recording is not supported in this browser.');
  });

  it('says why after the microphone is denied, and stays clickable so a granted mic works', async () => {
    // Disabling here would make voice unreachable for the rest of the session:
    // granting permission in site settings cannot re-enable a dead button, and
    // nothing on screen would say how to get it back.
    installRecordingStack({ deny: true });
    renderComposer();

    fireEvent.click(await screen.findByTestId('voice-record'));

    await waitFor(() =>
      expect(screen.getByTestId('voice-record')).toHaveAttribute(
        'title',
        'Microphone access is blocked.',
      ),
    );
    expect(toastError).toHaveBeenCalledWith('Microphone access is blocked.');
    expect(screen.getByTestId('voice-record')).not.toBeDisabled();
  });

  it('records the best container Respond.io accepts, never webm when there is a choice', async () => {
    installRecordingStack({ supported: ['audio/ogg;codecs=opus', 'audio/webm;codecs=opus'] });
    expect(pickVoiceMimeType()).toBe('audio/ogg;codecs=opus');

    installRecordingStack({ supported: ['audio/webm;codecs=opus'] });
    expect(pickVoiceMimeType()).toBe('audio/webm;codecs=opus');

    installRecordingStack({ supported: [] });
    expect(pickVoiceMimeType()).toBeNull();
  });
});

describe('voice helpers', () => {
  it('names the clip after the moment it was recorded, with the container extension', () => {
    const at = new Date(2026, 7, 16, 22, 31, 5);
    expect(voiceFileName('audio/mp4', at)).toBe('voice-message-20260816-223105.m4a');
    expect(voiceFileName('audio/ogg;codecs=opus', at)).toBe('voice-message-20260816-223105.ogg');
    expect(voiceFileName('audio/webm;codecs=opus', at)).toBe('voice-message-20260816-223105.webm');
  });

  it('formats the elapsed counter as mm:ss', () => {
    expect(formatElapsed(0)).toBe('0:00');
    expect(formatElapsed(9)).toBe('0:09');
    expect(formatElapsed(75)).toBe('1:15');
  });
});
