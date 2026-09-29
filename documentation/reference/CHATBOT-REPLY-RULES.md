# Chatbot reply text rules

Standing owner rulings that govern what the chatbot's WhatsApp reply text may say,
enforced in code and recorded here so the next editor can see the rule rather than
only its enforcement. None of the existing `documentation/reference/*.md` files
cover chatbot reply text specifically (`DESIGN-LANGUAGE.md` is frontend UI tokens
and motion, `ADR-PRODUCT-STANDARDS.md` is CRUD/UX for the web app) - this file is
the new home for rules of this shape.

## No paging text, ever

**The chatbot never prints paging text ("Showing N", "Showing X to Y") in a
reply.** A count names what was counted; it never claims to have shown a page of
it.

Owner ruling, issue #1262 (Samantha case), slice 3, finding F5: a stock ask that
matched nothing still swept the whole in-stock catalogue (5,857 products,
unscoped) and printed `"5,857 products have stock. Showing 0."` - a paging
fragment describing zero rows drawn against thousands of qualifying ones. The
sentence was not merely wrong; the owner's ruling is that this SHAPE of text
("Showing N") is banned outright from any chatbot reply, not only corrected for
that one case.

Enforced in `app/services/chatbot/lanes/business/answer.py::build_set_header`
(the counted-set header a HAS-turn prepends to its answer) - it names the count
and what was counted, and nothing about how many of them the reply is showing.
`build_set_page_header` (a `"more"` continuation page's own header) is a
different, narrower surface this ruling does not reach yet; removing its own
paging mode is a separate piece of work, not folded into this ruling.

A related cap, same finding: a miss line that names its own subject caps the list
at 5 codes (`lanes/business/fetch.py::_axis_labelled_subject`) - above the cap it
says "the N products searched" rather than naming every one, for the same reason
the paging text is banned: a customer-facing count is a fact, not an invitation to
scroll a list of hundreds.
