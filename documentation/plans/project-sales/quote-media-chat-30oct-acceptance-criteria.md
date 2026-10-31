# UAC: Drawing and photo requests use the chat escalation flow

Plan: `PLAN-quote-media-chat-30oct.md`.

- **AC-1** Two salespeople escalating the same product's drawing get two separate tickets, each
  routed on the general-enquiries route. The same salesperson escalating it again (any quotation)
  is added to their own open ticket and gets "Already escalated".
- **AC-2** When the salesperson's WhatsApp contact is linked, they receive exactly one WhatsApp per
  new ticket: `Your project request: technical drawing for <product code> (<quotation no>). Routed to your PIC, they will reply shortly.`
  (`product photo` for a photo request).
- **AC-3** The PIC opens the task from My pending tasks and sees, in the side panel, the product,
  the quotations waiting, Upload in Resources and the WhatsApp conversation with the salesperson,
  with a message box. There is no Respond button: the first reply marks the task responded.
- **AC-4** Resolve ticket closes the task the way a chat ticket closes: the salesperson gets the
  standard "your enquiry ... has been resolved" WhatsApp and the conversation is closed when they
  have no other open ticket.
- **AC-5** A salesperson with no linked WhatsApp contact gets no WhatsApp; the PIC sees today's
  panel with a Respond button; in-app and email notices work as before.
- **AC-6** The salesperson's "responded" and "resolved" notices arrive in-app and by email, never as
  a second WhatsApp.
- **AC-7** A file linked to the product in Resources notifies the PIC of every open ticket of that
  kind for that product.
- **AC-8** On the quotation, each salesperson's tile shows their own request: a colleague's open
  request does not hide Escalate.
