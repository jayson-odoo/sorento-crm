# PLAN - Chatbot: a linked contact is scoped to its customers; "my" / "me" means them

Status: mapping (29 Sep 2026; crew lane CHATBOT-CUSTOMER-SCOPE). Standard track: this is an
authorization boundary (security-reviewer runs). UAC: `chatbot-customer-scope-29sep-acceptance-criteria.md`.

Owner, verbatim (29 Sep 2026):

> after we have binded a contact to customer(s), they can only check the details relevant to
> the linked customer, meaning, it cannot ask about DO of other customer, outstanding for other
> customers, basically at the MCP layer, when we detect the customer_ids is not aligned with the
> linked customer, we need to block, or, even at the resolve entity layer which is a bit more
> upstream, i think better be upstream so we block as early as possible, and the chatbot needs
> to be able to understand when the user refer to "my", "me" etc, it means the customer, like
> what's my delivery, what's my xxx, the parser might need to emit this as a signal, for resolve
> entity processing to know hey, this contact is asking for his details, so need to find his
> linked customer etc etc

## Map of today's path (filled in below before any code)

(pending)
