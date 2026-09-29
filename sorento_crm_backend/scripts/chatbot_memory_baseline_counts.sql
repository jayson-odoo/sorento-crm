-- Chatbot memory lane A, Q18 / AC-MEM050 baseline.
--
-- Run on the 25 Sep prod copy (orchestrator step, this VM has no copy of it - contract
-- section 8, ruling 8). Three counts over LIVE turns (is_test = false) between 9 Sep and
-- 25 Sep 2026, over the customer's own message text (never the reply, never the parser's
-- derived verdict - the same `envelope -> message -> message -> message ->> text` path
-- `turn/memory.py::_turn_message_text` reads). Heuristic ILIKE phrase lists, not an
-- exhaustive NLU pass: good enough for "the baseline S4 is measured against" (AC-MEM050),
-- not a claim of complete recall. Extend the phrase lists here, in one place, if S4's own
-- measurement finds the baseline undercounts a language.
--
-- Usage: psql "$DATABASE_URL" -f scripts/chatbot_memory_baseline_counts.sql

WITH live_turns AS (
    SELECT
        id,
        envelope #>> '{message,message,message,text}' AS message_text
    FROM chatbot.turns
    WHERE is_test = false
      AND created_at >= '2026-09-09 00:00:00'
      AND created_at <  '2026-09-26 00:00:00'
)
SELECT
    -- 1. "the usual" or an equivalent (en / ms / zh).
    (
        SELECT count(*) FROM live_turns
        WHERE message_text ILIKE '%the usual%'
           OR message_text ILIKE '%as usual%'
           OR message_text ILIKE '%same as last time%'
           OR message_text ILIKE '%seperti biasa%'
           OR message_text ILIKE '%macam biasa%'
           OR message_text ILIKE '%biasa punya%'
           OR message_text ILIKE '%老样子%'
           OR message_text ILIKE '%照常%'
           OR message_text ILIKE '%和上次一样%'
    ) AS asks_for_the_usual,
    -- 2. A statement about the dealer themselves (role, usual products/brands/sites,
    --    project, a free "about" remark) - the profile_statement vocabulary's own cues.
    (
        SELECT count(*) FROM live_turns
        WHERE message_text ILIKE '%i am a%'
           OR message_text ILIKE '%i''m a%'
           OR message_text ILIKE '%i usually%'
           OR message_text ILIKE '%my project%'
           OR message_text ILIKE '%our site%'
           OR message_text ILIKE '%saya ialah%'
           OR message_text ILIKE '%saya selalu%'
           OR message_text ILIKE '%kami selalu%'
           OR message_text ILIKE '%projek saya%'
           OR message_text ILIKE '%我是%'
           OR message_text ILIKE '%我们通常%'
           OR message_text ILIKE '%我常常%'
    ) AS states_a_fact_about_the_dealer,
    -- 3. A question about their OWN history ("what did I order last time", "sebelum
    --    ini", "上次") - `history_question`'s own cue set (S3 schema addition).
    (
        SELECT count(*) FROM live_turns
        WHERE message_text ILIKE '%last time%'
           OR message_text ILIKE '%what did i%'
           OR message_text ILIKE '%what did we%'
           OR message_text ILIKE '%previously%'
           OR message_text ILIKE '%sebelum ini%'
           OR message_text ILIKE '%tempoh hari%'
           OR message_text ILIKE '%kali terakhir%'
           OR message_text ILIKE '%上次%'
           OR message_text ILIKE '%之前%'
           OR message_text ILIKE '%以前%'
    ) AS asks_about_own_history;
