# UAC: media intake guard

- UAC-1: a download whose first bytes are not a jpeg/png/webp/gif/heic image (for an image turn), a pdf
  (document), a video or an audio file fails the extraction job; the job error reads
  `Downloaded file is not a <modality>: content-type <ct>, <n> bytes, first bytes <hex>`.
- UAC-2: a real jpeg/png/webp/gif/heic/pdf passes the check unchanged.
- UAC-3: a completed image read with 0 items and no caption/text replies the existing "could not read
  anything" wording; the parser is not called.
- UAC-4: a completed read with 0 items but a caption still runs the parser on the caption.
- UAC-5: `stored_attachment` sends `mimeType` for a stored photo or voice note whose file name shows one
  (`chat_histories` keeps no mime column); any other attachment type sends none.
- UAC-6: a Gemini 402 or "credits depleted" error carries the operator hint, as 429 does.
- UAC-7: the turn trace shows the quoted turn as readable fields, never `[object Object]`.
