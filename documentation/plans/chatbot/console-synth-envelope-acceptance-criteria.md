# UAC: console-synth-envelope

1. A contact with a `respond_contacts` row and no real webhook turn gets a console reply;
   the response and trace carry `synthetic_envelope=true`; zero outbound sends.
2. A contact with no `respond_contacts` row and no turn still gets 404
   `CHATBOT_CONSOLE_NO_ENVELOPE`.
3. A contact with real history still borrows its webhook envelope; `synthetic_envelope` is false.
4. A console/test row is never borrowed (S6), and the synthetic base is never stored as a base.
5. Synthetic and borrowed envelopes give the same answer facts: stock allowed, customer
   links, company pick for a contact in two companies.
6. The phone lookup reads the default workspace's row when the respond id exists in two workspaces.
7. The console shows the badge "simulated contact, no real WhatsApp history" when the
   response says synthetic.
