/**
 * PHASE 1 PROTOTYPE FIXTURES — conversation intervention tickets.
 *
 * DEBT: this whole file (and every call to it from `interventionTicketService`)
 * is deleted in Phase 2 (S2.7), when the drawer runs off the real endpoints.
 * Nothing here may leak into shipped behaviour: it is in-memory, per-tab, and
 * resets on reload.
 *
 * State coverage (UAC AC-B1 / AC-C1 / AC-C2 / AC-D4):
 *   - fresh, near-breach, escalated, responded-awaiting-resolve, out-of-window
 *   - TWO open tickets for ONE contact (Aisyah Rahman) sharing one thread
 *   - inbound attachments (photo / document / audio), a sticker, an unknown
 *     message type, and a quoted reply
 *
 * Prototype state switches (query string, prototype-only):
 *   ?ticket_mock=empty         -> no tickets (widget empty state)
 *   ?ticket_mock=error         -> list/detail/thread reject (error states)
 *   ?ticket_mock=empty_thread  -> tickets load, threads come back with no messages
 */

import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';
import type {
  InterventionTicketDetail,
  InterventionTicketListItem,
  InterventionTicketThread,
  SendTicketMessageInput,
  SendTicketMessageResult,
} from '../interventionTicketService';

/**
 * Mock rows are merged into the live dashboard widget while Phase 1 runs, but
 * never under vitest — the existing widget suite asserts on the real
 * `/my-pending` payload and must stay green.
 */
export const phase1TicketMocksEnabled = process.env.NODE_ENV !== 'test';

const LATENCY_MS = 220;

type MockMode = 'normal' | 'empty' | 'error' | 'empty_thread';

function mockMode(): MockMode {
  if (typeof window === 'undefined') return 'normal';
  const value = new URLSearchParams(window.location.search).get('ticket_mock');
  if (value === 'empty' || value === 'error' || value === 'empty_thread') return value;
  return 'normal';
}

function settle<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), LATENCY_MS));
}

function fail<T>(message: string): Promise<T> {
  return new Promise((_resolve, reject) =>
    setTimeout(() => reject(new Error(message)), LATENCY_MS),
  );
}

const BOOT_MS = Date.now();

/** Naive-UTC string (the backend's wire format) `n` minutes from boot. */
function naiveUtc(minutesFromNow: number): string {
  const d = new Date(BOOT_MS + minutesFromNow * 60_000);
  return d.toISOString().replace('Z', '').replace(/\.\d+$/, '');
}

/** Respond.io message ids are microsecond epochs. */
function messageIdAt(minutesFromNow: number): number {
  return (BOOT_MS + minutesFromNow * 60_000) * 1000;
}

function incoming(minutesFromNow: number, message: Record<string, unknown>): RespondMessageRenderable {
  return {
    messageId: messageIdAt(minutesFromNow),
    traffic: 'incoming',
    message: message as RespondMessageRenderable['message'],
    status: [],
  };
}

function outgoing(
  minutesFromNow: number,
  message: Record<string, unknown>,
  source = 'user',
): RespondMessageRenderable {
  const ts = BOOT_MS + minutesFromNow * 60_000;
  return {
    messageId: messageIdAt(minutesFromNow),
    traffic: 'outgoing',
    message: message as RespondMessageRenderable['message'],
    sender: { source },
    status: [
      { value: 'sent', timestamp: ts },
      { value: 'delivered', timestamp: ts + 2_000 },
      { value: 'read', timestamp: ts + 45_000 },
    ],
  };
}

// ---------------------------------------------------------------------------
// Contacts + threads (a thread belongs to the CONTACT, shared by its tickets)
// ---------------------------------------------------------------------------

const AISYAH_TRIGGER_1 = messageIdAt(-170);
const AISYAH_TRIGGER_2 = messageIdAt(-38);

const THREADS: Record<string, RespondMessageRenderable[]> = {
  aisyah: [
    incoming(-185, { type: 'text', text: 'Hi, do you still carry the 60x60 marble-look tile?' }),
    outgoing(
      -184,
      {
        type: 'text',
        text: 'Hello! I can check that for you. Would you like to speak to our team?',
      },
      'bot',
    ),
    incoming(-178, {
      type: 'attachment',
      attachment: { type: 'image', url: '/media/images/600x400/8.jpg' },
      text: 'This is the one I saw in your showroom.',
    }),
    incoming(-170, { type: 'text', text: 'Yes, please connect me to a person.' }),
    outgoing(
      -169,
      { type: 'text', text: 'Sure - one of our team members will be with you shortly.' },
      'bot',
    ),
    incoming(-60, {
      type: 'sticker',
      attachment: { type: 'sticker', url: 'https://cdn.example.com/stickers/thumbs-up.webp' },
    }),
    incoming(-38, {
      type: 'text',
      text: 'Also, can someone quote installation for 3 bathrooms?',
    }),
    incoming(-36, {
      // Deliberately a type the UI has never seen: it must still render a
      // placeholder rather than a blank bubble (UAC AC-D4).
      type: 'contactCard',
      contact: { name: 'Site supervisor', phone: '+60 12-909 1122' },
    }),
  ],
  daniel: [
    incoming(-320, { type: 'text', text: 'My delivery yesterday was short by 2 boxes.' }),
    incoming(-318, {
      type: 'attachment',
      attachment: { type: 'file', url: '/media/file-types/pdf.svg', fileName: 'DO-2026-0442.pdf' },
    }),
    outgoing(-300, {
      type: 'text',
      text: '> My delivery yesterday was short by 2 boxes.\nThank you, I am checking this with the warehouse now.',
    }),
    incoming(-120, {
      type: 'attachment',
      attachment: { type: 'audio', url: 'https://cdn.example.com/audio/voice-note.ogg' },
    }),
  ],
  siti: [
    incoming(-240, {
      type: 'text',
      text: 'Hi, I need the warranty certificate for order SO-2026-0442.',
    }),
    outgoing(-90, {
      type: 'text',
      text: 'Certainly - I am preparing the certificate now and will send it shortly.',
    }),
  ],
  ravi: [
    incoming(-4_600, { type: 'text', text: 'Do you deliver to Kota Kinabalu?' }),
    outgoing(-4_590, { type: 'text', text: 'Yes we do. May I know the delivery address?' }, 'bot'),
    incoming(-4_580, { type: 'text', text: 'Let me confirm with my contractor first.' }),
  ],
};

// ---------------------------------------------------------------------------
// Tickets
// ---------------------------------------------------------------------------

interface MockTicket {
  contactKey: keyof typeof THREADS;
  list: InterventionTicketListItem;
  detail: InterventionTicketDetail;
}

function makeTicket(args: {
  id: string;
  contactKey: keyof typeof THREADS;
  contactName: string;
  contactPhone: string;
  respondIoId: string;
  snippet: string;
  sourceMessageId: number;
  sourceMessageAt: number;
  team: string;
  policy: string;
  assignee: string;
  initiatedMinutes: number;
  dueMinutes: number | null;
  dueResolutionMinutes: number | null;
  tier: number;
  escalatedMinutes?: number | null;
  escalationReason?: string | null;
  respondedMinutes?: number | null;
  windowOpen: boolean;
  windowExpiresMinutes?: number | null;
}): MockTicket {
  const responded = args.respondedMinutes != null;
  const dueAt = args.dueMinutes != null ? naiveUtc(args.dueMinutes) : null;
  const dueResolution =
    args.dueResolutionMinutes != null ? naiveUtc(args.dueResolutionMinutes) : null;
  const escalatedAt = args.escalatedMinutes != null ? naiveUtc(args.escalatedMinutes) : null;
  const respondedAt = responded ? naiveUtc(args.respondedMinutes as number) : null;

  const list: InterventionTicketListItem = {
    id: args.id,
    is_intervention_ticket: true,
    is_form_sla: false,
    source_entity_type: null,
    source_entity_id: null,
    reference: args.contactName,
    respond_io_id: args.respondIoId,
    next_action: null,
    due_at: dueAt,
    due_at_resolution: dueResolution,
    active_due_at: responded ? dueResolution : dueAt,
    due_kind: responded ? 'resolve' : 'respond',
    responded_at: respondedAt,
    is_responded: responded,
    current_tier: args.tier,
    policy_name: args.policy,
    takeover: null,
    contact_name: args.contactName,
    contact_phone: args.contactPhone,
    enquiry_snippet: args.snippet,
    source_message_id: String(args.sourceMessageId),
    team_label: args.team,
    initiated_at: naiveUtc(args.initiatedMinutes),
    escalated_at: escalatedAt,
  };

  const detail: InterventionTicketDetail = {
    id: args.id,
    contact_name: args.contactName,
    contact_phone: args.contactPhone,
    respond_io_id: args.respondIoId,
    source_message_id: String(args.sourceMessageId),
    source_message_text: args.snippet,
    source_message_at: naiveUtc(args.sourceMessageAt),
    team_label: args.team,
    assignee_name: args.assignee,
    policy_name: args.policy,
    initiated_at: naiveUtc(args.initiatedMinutes),
    current_tier: args.tier,
    escalated_at: escalatedAt,
    escalation_reason: args.escalationReason ?? null,
    due_at: dueAt,
    due_at_resolution: dueResolution,
    is_responded: responded,
    responded_at: respondedAt,
    is_resolved: false,
    resolved_at: null,
    can_send: true,
    can_resolve: true,
    send_capabilities: ['text', 'attachment'],
    window: {
      open: args.windowOpen,
      expires_at:
        args.windowExpiresMinutes != null ? naiveUtc(args.windowExpiresMinutes) : null,
    },
    chat_template: args.windowOpen
      ? null
      : {
          configured: true,
          template_name: 'conversation_chat_reply',
          body_text:
            'Hi {{1}}, this is {{2}} from Sorento. {{3}} Reply to this message to continue the conversation.',
          slots: {
            '1': { variable: 'contact_name', value: args.contactName, editable: false },
            '2': { variable: 'sender_name', value: args.assignee, editable: false },
            '3': { variable: 'message', value: null, editable: true },
          },
        },
  };

  return { contactKey: args.contactKey, list, detail };
}

const TICKETS: MockTicket[] = [
  // Fresh - plenty of clock left.
  makeTicket({
    id: 'mock-ticket-aisyah-stock',
    contactKey: 'aisyah',
    contactName: 'Aisyah Rahman',
    contactPhone: '+60 12-334 5566',
    respondIoId: '10025531',
    snippet: 'Yes, please connect me to a person.',
    sourceMessageId: AISYAH_TRIGGER_1,
    sourceMessageAt: -170,
    team: 'Customer Service - Tier 1',
    policy: 'Conversation SLA - Standard',
    assignee: 'You',
    initiatedMinutes: -170,
    dueMinutes: 46,
    dueResolutionMinutes: 350,
    tier: 1,
    windowOpen: true,
    windowExpiresMinutes: 1_402,
  }),
  // Same contact, second enquiry - near breach.
  makeTicket({
    id: 'mock-ticket-aisyah-install',
    contactKey: 'aisyah',
    contactName: 'Aisyah Rahman',
    contactPhone: '+60 12-334 5566',
    respondIoId: '10025531',
    snippet: 'Also, can someone quote installation for 3 bathrooms?',
    sourceMessageId: AISYAH_TRIGGER_2,
    sourceMessageAt: -38,
    team: 'Sales - Tier 1',
    policy: 'Conversation SLA - Standard',
    assignee: 'You',
    initiatedMinutes: -38,
    dueMinutes: 4,
    dueResolutionMinutes: 480,
    tier: 1,
    windowOpen: true,
    windowExpiresMinutes: 1_402,
  }),
  // Escalated + response clock already breached.
  makeTicket({
    id: 'mock-ticket-daniel-shortage',
    contactKey: 'daniel',
    contactName: 'Daniel Lim',
    contactPhone: '+60 16-882 1109',
    respondIoId: '10025612',
    snippet: 'My delivery yesterday was short by 2 boxes.',
    sourceMessageId: messageIdAt(-320),
    sourceMessageAt: -320,
    team: 'Customer Service - Tier 2',
    policy: 'Conversation SLA - Priority',
    assignee: 'You',
    initiatedMinutes: -320,
    dueMinutes: -22,
    dueResolutionMinutes: 120,
    tier: 2,
    escalatedMinutes: -20,
    escalationReason: 'auto: response deadline breached',
    windowOpen: true,
    windowExpiresMinutes: 1_120,
  }),
  // Responded - only the resolution clock is still running.
  makeTicket({
    id: 'mock-ticket-siti-warranty',
    contactKey: 'siti',
    contactName: 'Siti Nurhaliza',
    contactPhone: '+60 19-770 4412',
    respondIoId: '10025744',
    snippet: 'I need the warranty certificate for order SO-2026-0442.',
    sourceMessageId: messageIdAt(-240),
    sourceMessageAt: -240,
    team: 'Customer Service - Tier 1',
    policy: 'Conversation SLA - Standard',
    assignee: 'You',
    initiatedMinutes: -240,
    dueMinutes: -150,
    dueResolutionMinutes: 92,
    tier: 1,
    respondedMinutes: -90,
    windowOpen: true,
    windowExpiresMinutes: 1_350,
  }),
  // Messaging window closed - composer falls back to the template fill-in.
  makeTicket({
    id: 'mock-ticket-ravi-delivery',
    contactKey: 'ravi',
    contactName: 'Ravi Kumar',
    contactPhone: '+60 13-556 8890',
    respondIoId: '10025809',
    snippet: 'Let me confirm with my contractor first.',
    sourceMessageId: messageIdAt(-4_580),
    sourceMessageAt: -4_580,
    team: 'Sales - Tier 1',
    policy: 'Conversation SLA - Standard',
    assignee: 'You',
    initiatedMinutes: -4_580,
    dueMinutes: 180,
    dueResolutionMinutes: 900,
    tier: 1,
    windowOpen: false,
    windowExpiresMinutes: -3_140,
  }),
];

// Mutable prototype state: sends append to a thread + stop a response clock,
// resolve drops the ticket from the worklist.
const store = {
  tickets: TICKETS.map((t) => ({ ...t, list: { ...t.list }, detail: { ...t.detail } })),
  threads: Object.fromEntries(
    Object.entries(THREADS).map(([k, v]) => [k, [...v]]),
  ) as Record<string, RespondMessageRenderable[]>,
};

function find(id: string): MockTicket | undefined {
  return store.tickets.find((t) => t.list.id === id);
}

export async function mockGetMyInterventionTickets(): Promise<InterventionTicketListItem[]> {
  const mode = mockMode();
  if (mode === 'error') return fail('Failed to load your intervention tickets');
  if (mode === 'empty') return settle([]);
  return settle(store.tickets.map((t) => ({ ...t.list })));
}

export async function mockGetInterventionTicket(id: string): Promise<InterventionTicketDetail> {
  if (mockMode() === 'error') return fail('Failed to load this ticket');
  const ticket = find(id);
  if (!ticket) return fail('Ticket not found');
  return settle({ ...ticket.detail });
}

export async function mockGetInterventionTicketThread(
  id: string,
): Promise<InterventionTicketThread> {
  const mode = mockMode();
  if (mode === 'error') return fail('Failed to load the conversation');
  const ticket = find(id);
  if (!ticket) return fail('Ticket not found');
  if (mode === 'empty_thread') return settle({ items: [] });
  return settle({ items: [...(store.threads[ticket.contactKey] ?? [])] });
}

export async function mockSendInterventionTicketMessage(
  id: string,
  input: SendTicketMessageInput,
): Promise<SendTicketMessageResult> {
  const ticket = find(id);
  if (!ticket) return fail('Ticket not found');

  const windowOpen = ticket.detail.window.open;
  const files = input.attachments ?? [];
  const sentAt = Date.now();
  const message: Record<string, unknown> = { type: 'text', text: input.text };
  if (files.length > 0) {
    message.type = 'attachment';
    message.attachment = files.map((file) => ({
      type: file.type.startsWith('image/')
        ? 'image'
        : file.type.startsWith('video/')
          ? 'video'
          : file.type.startsWith('audio/')
            ? 'audio'
            : 'file',
      url: URL.createObjectURL(file),
      fileName: file.name,
    }));
  }
  store.threads[ticket.contactKey] = [
    ...(store.threads[ticket.contactKey] ?? []),
    {
      messageId: sentAt * 1000,
      traffic: 'outgoing',
      message: message as RespondMessageRenderable['message'],
      sender: { source: 'user' },
      status: [{ value: 'sent', timestamp: sentAt }],
    },
  ];

  // The send stamps THIS ticket only - a sibling for the same contact keeps its
  // own running response clock (UAC AC-E1).
  if (!ticket.list.is_responded) {
    const respondedAt = naiveUtc(0);
    ticket.list.is_responded = true;
    ticket.list.responded_at = respondedAt;
    ticket.list.due_kind = 'resolve';
    ticket.list.active_due_at = ticket.list.due_at_resolution;
    ticket.detail.is_responded = true;
    ticket.detail.responded_at = respondedAt;
  }

  return settle({
    sent_as: files.length > 0 ? 'attachment' : windowOpen ? 'text' : 'template',
    rendered_text: input.text,
    flattened: !windowOpen && /[\n\t]|\s{2,}/.test(input.text),
    window: ticket.detail.window,
  });
}

export async function mockResolveInterventionTicket(id: string): Promise<void> {
  const ticket = find(id);
  if (!ticket) return fail('Ticket not found');
  await settle(null);
  store.tickets = store.tickets.filter((t) => t.list.id !== id);
}
