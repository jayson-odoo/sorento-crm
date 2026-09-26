# UAC: a contact's turns are answered in WhatsApp send order (issue #1262 round 3)

Plan: `PLAN-chatbot-turn-order-by-send-time.md`. Tests:
`sorento_crm_backend/tests/chatbot/test_turn_order_by_send_time.py` (`T::` below).

- AC-1 Mr Loo's photo (sent 14:57:25) and "Stock" (sent 14:57:29), with "Stock" reaching
  `/chat/turn` first while n8n is still extracting the photo: the photo is answered first,
  "Stock" is parsed against the photo's products, and the photo's reply is the first message
  sent. `T::TestPhotoStillInN8nMediaIntake::test_mr_loo_photo_is_answered_first_and_stock_applies_to_its_products`
- AC-2 The photo's own later delivery is a duplicate: no second parse, nothing sent.
  `T::TestPhotoStillInN8nMediaIntake::test_the_photos_own_late_delivery_is_a_duplicate_and_sends_nothing`
- AC-3 A photo whose extraction already finished and never became a turn is never answered
  by a later message. `T::...::test_a_photo_whose_extraction_already_finished_is_not_replayed`
- AC-4 A job stranded before a turn that has since been answered is never replayed.
  `T::...::test_a_stranded_job_from_before_an_answered_turn_is_not_replayed`
- AC-5 Both messages in the per-contact queue: the earlier-sent one waiting behind is answered
  first; a later-sent one is left to its own request.
  `T::TestBothInThePerContactQueue::test_a_queued_earlier_sent_message_is_answered_before_the_one_holding_the_slot`,
  `T::TestBothInThePerContactQueue::test_a_queued_later_sent_message_is_left_for_its_own_request`
- AC-6 Ordering on: the waiting request whose message was answered ahead of it replays that
  answer as a duplicate, including after a queue timeout (no generic error reply).
  `T::TestOrderingOnTheWaitingRequest::test_the_waiting_photo_request_replays_the_answer_given_ahead_of_it`,
  `T::TestOrderingOnTheWaitingRequest::test_a_queue_timeout_after_being_answered_ahead_sends_no_error_reply`
- AC-7 Owner ruling 26 Sep: no stale-focus guard. A bare "Stock" on a focus left by a turn on
  an earlier Kuala Lumpur day still answers from that focus, with no re-ask for a product.
  `T::TestCarriedFocusAcrossDays::test_bare_stock_on_a_focus_from_an_earlier_kuala_lumpur_day_still_answers_it`
- AC-9 A queued row stuck before an answered turn is never replayed.
  `T::TestReviewRound1::test_a_queued_row_stuck_before_an_answered_turn_is_never_replayed`
- AC-10 The pre-step is best effort: a failure keeps earlier answers and this turn.
  `T::TestReviewRound1::test_a_failure_taking_a_second_earlier_message_keeps_the_first_answer_and_this_turn`,
  `T::TestReviewRound1::test_a_failing_lookup_answers_this_turn_alone`
- AC-11 D14: a dry run never claims or answers a live message.
  `T::TestReviewRound1::test_a_dry_run_never_claims_or_answers_live_messages`
