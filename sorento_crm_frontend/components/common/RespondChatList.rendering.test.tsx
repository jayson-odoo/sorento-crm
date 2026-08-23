import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import RespondChatList from './RespondChatList';
import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';

/**
 * What a bubble is allowed to show (the audit of 2026-08-22).
 *
 * Every fixture here is a real message shape taken from this workspace's own
 * Respond.io history, and each test pins one thing the thread used to get wrong:
 * quick replies rendering as "(no text)", WhatsApp markup showing its markers,
 * links not being links, template buttons vanishing, and bubbles labelled with
 * the transport ("n8n") or with the word "Contact".
 */

const BASE_US = 1787356488600956;

function msg(index: number, patch: Partial<RespondMessageRenderable>): RespondMessageRenderable {
  return {
    messageId: BASE_US + index,
    traffic: 'outgoing',
    message: { type: 'text', text: 'hello' },
    ...patch,
  };
}

describe('quick_reply messages', () => {
  const quickReply = msg(1, {
    sender: { source: 'n8n' },
    message: {
      type: 'quick_reply',
      title: 'No stock for SRTW2600-SS-CR. Reply with a code to continue.',
      replies: ['SRTW2600', 'SRTW2600-BL', 'Yes escalate'],
    },
  });

  it('renders the prompt body instead of "(no text)"', () => {
    render(<RespondChatList items={[quickReply]} />);
    expect(
      screen.getByText(/No stock for SRTW2600-SS-CR\. Reply with a code to continue\./),
    ).toBeInTheDocument();
    expect(screen.queryByText('(no text)')).not.toBeInTheDocument();
  });

  it('lists every option the contact was offered', () => {
    render(<RespondChatList items={[quickReply]} />);
    for (const option of ['SRTW2600', 'SRTW2600-BL', 'Yes escalate']) {
      expect(screen.getByText(option)).toBeInTheDocument();
    }
  });
});

describe('WhatsApp markup', () => {
  it('styles *bold* and _italic_ and hides the markers', () => {
    render(
      <RespondChatList
        items={[
          msg(2, {
            message: {
              type: 'text',
              text: '*Product Code:* SRTFC2032\n_Data last updated: 14/05/2026_',
            },
          }),
        ]}
      />,
    );

    const bold = screen.getByText('Product Code:');
    expect(bold.tagName).toBe('STRONG');
    const italic = screen.getByText('Data last updated: 14/05/2026');
    expect(italic.tagName).toBe('EM');
    expect(screen.queryByText(/\*Product Code:\*/)).not.toBeInTheDocument();
  });

  it('leaves an underscore inside a word alone', () => {
    const text = 'PROMO_07052026 DEALER and CODE_12345 too';
    render(<RespondChatList items={[msg(3, { message: { type: 'text', text } })]} />);
    expect(screen.getByText(text)).toBeInTheDocument();
  });
});

describe('links', () => {
  it('makes a bare url clickable, opening in a new tab', () => {
    render(
      <RespondChatList
        items={[
          msg(4, {
            message: { type: 'text', text: 'Portal: https://fe-sorento.foundryx.my/portal/c/AB12' },
          }),
        ]}
      />,
    );

    const link = screen.getByRole('link', {
      name: 'https://fe-sorento.foundryx.my/portal/c/AB12',
    });
    expect(link).toHaveAttribute('href', 'https://fe-sorento.foundryx.my/portal/c/AB12');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });
});

describe('whatsapp_template buttons', () => {
  it('shows the url button the contact was handed, as a link', () => {
    render(
      <RespondChatList
        items={[
          msg(5, {
            sender: { source: 'n8n' },
            message: {
              type: 'whatsapp_template',
              text: '*Complaint No - CMP26-0181*\nUpdate: Arrange Technician to attend.',
              template: {
                name: 'complaint_update_with_button',
                components: [
                  { type: 'body', text: '*Complaint No - CMP26-0181*' },
                  {
                    type: 'buttons',
                    buttons: [
                      {
                        type: 'url',
                        text: 'View',
                        url: 'https://fe-sorento.foundryx.my/portal/c/VWRW980G6B/complaint/3f871885',
                      },
                    ],
                  },
                ],
              },
            },
          }),
        ]}
      />,
    );

    expect(screen.getByTestId('template-buttons')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View' })).toHaveAttribute(
      'href',
      'https://fe-sorento.foundryx.my/portal/c/VWRW980G6B/complaint/3f871885',
    );
  });
});

describe('sender labels', () => {
  it('never labels a bot send with the transport that carried it', () => {
    render(
      <RespondChatList
        items={[msg(6, { sender: { source: 'n8n' }, message: { type: 'text', text: 'sent' } })]}
      />,
    );
    expect(screen.queryByText('n8n')).not.toBeInTheDocument();
    expect(screen.queryByText('User')).not.toBeInTheDocument();
  });

  it('names the colleague behind a human send', () => {
    render(
      <RespondChatList
        items={[
          msg(7, {
            sender: { source: 'user', name: 'Tay Zhi Yang' },
            message: { type: 'text', text: 'Here is the drawing' },
          }),
        ]}
      />,
    );
    expect(screen.getByText('Tay Zhi Yang')).toBeInTheDocument();
  });

  it('falls back to no label when a human send has no resolvable name', () => {
    const { container } = render(
      <RespondChatList
        items={[
          msg(8, { sender: { source: 'user' }, message: { type: 'text', text: 'anonymous' } }),
        ]}
      />,
    );
    expect(container.querySelector('.text-emerald-700')).toBeNull();
  });

  it('does not label an incoming bubble "Contact"', () => {
    render(
      <RespondChatList
        contactName="Ah Seng Hardware"
        items={[
          msg(9, {
            traffic: 'incoming',
            sender: { source: 'contact' },
            message: { type: 'text', text: 'SRTW2600-BL please' },
          }),
        ]}
      />,
    );
    expect(screen.queryByText('Contact')).not.toBeInTheDocument();
    expect(screen.getByText('SRTW2600-BL please')).toBeInTheDocument();
  });
});
