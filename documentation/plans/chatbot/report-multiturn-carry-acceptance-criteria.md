# UAC: multi-turn carry for report asks (crew ruling 2 Nov: Q1-Q3 a)

The owner's conversation, his words with the two agents masked (AGENT A, AGENT B), on a staff contact in two companies. Each line: what the bot must do.

- **MC-1** "sales for agent a for cabana 2026" asks the basis; "ivoiced" asks "Cabana: brand or account type?"; "account type"
  runs AGENT A, CABANA, 2026, invoiced. (Works today; must keep working.)
- **MC-2** "breka down by month" runs the same by month; "for ceramic" runs CERAMIC with the rest kept. (Works today.)
- **MC-3** "for slaes agent agent b" runs AGENT B in place of AGENT A, CERAMIC, by month, 2026, invoiced: no question.
- **MC-4** "this year" runs the same with period 2026: no company question.
- **MC-5** A company answer ("sorento") keeps every other slot of the open ask.
- **MC-6** A follow-up naming an agent never asks the basis again once the conversation set it.
- **MC-7** "for ceramic account ty[e" (account type said) with Sorento held: CERAMIC, Sorento kept, no company question, no
  "brand or account type?".
- **MC-8** "breakd down by month, only sales agent agent b": by month, AGENT B, the period kept: no period question.
- **MC-9** A company answer the parser also reads as a brand word is the company answer, never a "brand or account type?".
- **MC-11** Q1: a held company stays on a follow-up naming an agent, type or brand that exists in it; when the subject
  exists only in the other company, the company is dropped and asked ("Sorento or Mocha?").
- **MC-12** Q3: a follow-up of another report kind (stock, product info, a document list) or a parser-marked reset starts
  clean; a stale frame carries nothing (existing rule).
- **MC-10** Unchanged: #2070 held customer and its AC; #2074 AT-20 to AT-37; basis asked on a conversation's first ask;
  outstanding summary shape.
