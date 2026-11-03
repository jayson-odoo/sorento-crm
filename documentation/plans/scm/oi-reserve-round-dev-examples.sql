-- OI-RESERVE-ROUND: read-only queries for the behaviour card's real examples (dev DB, prod copy).
-- SELECT only. Crew runs these and pastes the output into the PR; nothing here writes.

-- Q-A. Recent request "sends": requests grouped by who asked and the minute they were sent.
-- A multi-OI "Request CS to reserve" (Stock Debt / OI list) creates one request per OI, so a
-- group of N rows here is what the owner calls one round. parked_at is cleared on send, so
-- requested_at is the create time (park time for a parked request), not the send time.
SELECT u.name AS requester,
       date_trunc('minute', r.requested_at) AS asked_minute,
       count(*) AS requests,
       count(DISTINCT oi.raised_by) AS raisers,
       string_agg(DISTINCT oi.inquiry_no, ',' ORDER BY oi.inquiry_no) AS inquiries
FROM projects.order_inquiry_reserve_requests r
JOIN projects.order_inquiries oi ON oi.id = r.order_inquiry_id
LEFT JOIN users u ON u.id = r.requested_by
WHERE r.requested_at >= now() - interval '21 days'
GROUP BY 1, 2
ORDER BY 2 DESC
LIMIT 30;

-- Q-B. Per request row: what was asked, what CS answered, by whom and when (event trail).
-- Shows partial (0 < reserved < asked), rejected (0) and still open (NULL) lines.
SELECT oi.inquiry_no, r.ordinal, r.state, rq.name AS requester, ra.name AS raiser,
       row.item_code, rr.qty_requested, rr.qty_reserved, rr.notified_qty, rr.reason,
       (SELECT string_agg(e.kind || ' ' || e.qty::text || ' by ' || coalesce(a.name, '?') || ' @ '
                          || to_char(e.created_at, 'DD Mon HH24:MI'), '; ' ORDER BY e.created_at)
          FROM projects.order_inquiry_reserve_events e
          LEFT JOIN users a ON a.id = e.actor_id
         WHERE e.reserve_request_row_id = rr.id) AS trail
FROM projects.order_inquiry_reserve_request_rows rr
JOIN projects.order_inquiry_reserve_requests r ON r.id = rr.request_id
JOIN projects.order_inquiries oi ON oi.id = r.order_inquiry_id
JOIN projects.order_inquiry_rows row ON row.id = rr.row_id
LEFT JOIN users rq ON rq.id = r.requested_by
LEFT JOIN users ra ON ra.id = oi.raised_by
WHERE r.requested_at >= now() - interval '21 days'
ORDER BY r.requested_at DESC, oi.inquiry_no, row.item_code
LIMIT 200;

-- Q-C. The 3 Nov case: OI-2609-0404 (5 reserved emails in 4 minutes on prod).
SELECT r.ordinal, r.state, row.item_code, rr.qty_requested, rr.qty_reserved,
       e.kind, e.qty, e.created_at, a.name AS actor
FROM projects.order_inquiries oi
JOIN projects.order_inquiry_reserve_requests r ON r.order_inquiry_id = oi.id
JOIN projects.order_inquiry_reserve_request_rows rr ON rr.request_id = r.id
JOIN projects.order_inquiry_rows row ON row.id = rr.row_id
LEFT JOIN projects.order_inquiry_reserve_events e ON e.reserve_request_row_id = rr.id
LEFT JOIN users a ON a.id = e.actor_id
WHERE oi.inquiry_no = 'OI-2609-0404'
ORDER BY e.created_at;

-- Q-D. Same OI asked twice (a second round on the same OI), and lines asked in both.
SELECT oi.inquiry_no, row.item_code, count(*) AS times_asked,
       string_agg(r.ordinal::text || ':' || coalesce(rr.qty_reserved::text, 'open'), ', ' ORDER BY r.ordinal) AS answers
FROM projects.order_inquiry_reserve_request_rows rr
JOIN projects.order_inquiry_reserve_requests r ON r.id = rr.request_id
JOIN projects.order_inquiries oi ON oi.id = r.order_inquiry_id
JOIN projects.order_inquiry_rows row ON row.id = rr.row_id
GROUP BY 1, 2
HAVING count(*) > 1
ORDER BY 1 DESC
LIMIT 20;

-- Q-E. Lines asked to reserve that are ALSO covered by a PO/SPO/incoming link (the
-- "maybe in incoming, but hard to see" case): still open, or rejected.
SELECT oi.inquiry_no, row.item_code, rr.qty_requested, rr.qty_reserved, rr.reason,
       string_agg(l.document || ' x' || l.qty::text, ', ') AS other_cover
FROM projects.order_inquiry_reserve_request_rows rr
JOIN projects.order_inquiry_reserve_requests r ON r.id = rr.request_id
JOIN projects.order_inquiries oi ON oi.id = r.order_inquiry_id
JOIN projects.order_inquiry_rows row ON row.id = rr.row_id
JOIN projects.order_inquiry_links l ON l.row_id = row.id AND l.reserve_request_row_id IS NULL
WHERE coalesce(rr.qty_reserved, 0) = 0
GROUP BY 1, 2, 3, 4, 5
ORDER BY 1 DESC
LIMIT 30;

-- Q-F. Which reserve email templates does this DB hold? A subject still containing
-- "#{{ reserve.ordinal }}" means RESERVE-EMAIL-FULL-TABLE (#2046, oisn_0002) has not reached
-- this DB, or the guarded migration skipped an admin-edited template. Run on prod too: the
-- 3 Nov 16:32 emails still read "Reserved: OI-2609-0404 #1 - SO414932" (the pre-#2046 subject).
SELECT code, subject, updated_at
FROM email_templates
WHERE code LIKE 'order_inquiry_reserve%';

-- Q-G. The reserved emails actually queued per OI per day (email_outbox).
SELECT date_trunc('day', created_at) AS day, subject, count(*) AS emails
FROM email_outbox
WHERE subject LIKE 'Reserved:%'
GROUP BY 1, 2
ORDER BY 1 DESC, 3 DESC
LIMIT 30;
