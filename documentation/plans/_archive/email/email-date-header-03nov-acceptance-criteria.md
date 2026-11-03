# UAC: EMAIL-DATE-HEADER

1. Every message any backend sender hands to SMTP has exactly one `Date` header, in Malaysia
   time (+0800), equal to the send time.
2. Every such message has exactly one `Message-ID` of the form `<...@<sender domain>>`, unique
   per send; a sender with no domain still gets a valid Message-ID.
3. Subject, From, To, Cc, bodies and attachments are byte-for-byte what they were before.
4. In Outlook, a CRM email shows its sent date/time instead of "None".
