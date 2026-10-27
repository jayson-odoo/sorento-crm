# PLAN: sales total asks the basis (SALES-TOTAL-ASK)

Status: in progress (small fix track: chatbot, no migration, no auth change)

## Ruling

Owner, 27 Oct ~23:35 MYT: "total sales should ask". A chatbot question for a sales TOTAL
("total sales for X in Jan") asks the basis exactly like a sales ranking already does:
"Invoiced, delivered, ordered or outstanding?", Invoiced listed first. It never silently
defaults to Invoiced, and Outstanding is never defaulted either.

## Findings

(filled in as the code is read; every claim cites file:line)
