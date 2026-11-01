# UAC: Invoiced tab Channel column fast

1. On a seeded month (about 50,000 invoice lines), the Invoiced detail with all columns answers in
   about the time it takes without the Channel column (target under 20 s on the dev copy).
2. Every line's Channel value is identical to main's (count and checksum over a sample month).
3. Filtering by Channel returns the same lines as before.
4. No screen wording changes.
