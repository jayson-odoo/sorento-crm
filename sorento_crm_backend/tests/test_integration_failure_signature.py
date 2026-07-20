"""Failure-signature grouping for the health dashboard.

Covers UAC OBS-S1-11 .. OBS-S1-14.

Knowing a channel failed 5 times is not actionable — the dashboard has to say
*what* failed. Raw `error_message` cannot be the grouping key: it carries record
ids, timestamps and payload echoes, so 5 instances of one fault render as 5
distinct one-off errors. Normalising the volatile parts collapses them back into
the single signature they actually are.

The opposite failure matters just as much: over-normalising merges two genuinely
different faults into one line and hides the rarer one. So only demonstrably
volatile tokens are masked (uuids, digit runs, quoted timestamps) — never words.
"""
import pytest

from app.services.integration_failure_signature import normalize, top_failures


# --------------------------------------------------------------------------- #
# Normalisation — collapse volatile tokens                                    #
# --------------------------------------------------------------------------- #
def test_uuids_are_masked():
    a = normalize("Order 3f2b1c4e-9a1d-4f7e-88aa-1b2c3d4e5f60 not found")
    b = normalize("Order 99999999-0000-4111-8222-333333333333 not found")
    assert a == b


def test_digit_runs_are_masked():
    assert normalize("timeout after 30412ms") == normalize("timeout after 51ms")


def test_iso_timestamps_are_masked():
    a = normalize("no window at 2026-07-19T04:11:02")
    b = normalize("no window at 2026-01-02T23:59:59")
    assert a == b


def test_case_and_whitespace_are_normalised():
    assert normalize("  Connection   REFUSED ") == normalize("connection refused")


def test_distinct_faults_do_not_merge():
    """Masking must not swallow the words that distinguish two faults."""
    assert normalize("connection refused") != normalize("connection reset")


def test_status_code_participates_in_the_signature():
    """Same prose, different HTTP code = different fault to chase."""
    rows = [
        _Row(status_code=401, error_message="Unauthorized"),
        _Row(status_code=403, error_message="Unauthorized"),
    ]
    assert len(top_failures(rows)) == 2


def test_none_message_is_stable():
    assert normalize(None) == normalize("")


# --------------------------------------------------------------------------- #
# Aggregation — what the card renders                                         #
# --------------------------------------------------------------------------- #
class _Row:
    def __init__(self, status_code=None, error_message=None, count=1):
        self.status_code = status_code
        self.error_message = error_message
        self.count = count


def test_identical_faults_collapse_and_sum():
    rows = [
        _Row(status_code=500, error_message="Order 3f2b1c4e-9a1d-4f7e-88aa-1b2c3d4e5f60 failed", count=3),
        _Row(status_code=500, error_message="Order 99999999-0000-4111-8222-333333333333 failed", count=2),
    ]
    out = top_failures(rows)
    assert len(out) == 1
    assert out[0].count == 5


def test_sorted_by_count_desc():
    rows = [
        _Row(status_code=500, error_message="rare", count=1),
        _Row(status_code=502, error_message="common", count=9),
    ]
    assert [f.count for f in top_failures(rows)] == [9, 1]


def test_limit_caps_the_list():
    rows = [_Row(status_code=500, error_message=f"fault {w}", count=i) for i, w in enumerate("abcdef")]
    assert len(top_failures(rows, limit=3)) == 3


def test_sample_message_keeps_the_readable_original():
    """Group by the normalised key, but show a real message — a masked string
    like 'order <id> failed' is not something you can paste into a search."""
    rows = [_Row(status_code=500, error_message="Order 3f2b1c4e-9a1d-4f7e-88aa-1b2c3d4e5f60 failed", count=1)]
    assert "3f2b1c4e" in top_failures(rows)[0].sample_message


def test_long_message_is_truncated_for_display():
    rows = [_Row(status_code=500, error_message="x" * 900, count=1)]
    assert len(top_failures(rows)[0].sample_message) <= 300


def test_httpx_boilerplate_is_trimmed_from_the_display_message():
    """Every httpx failure carries the same MDN link. It identifies nothing and
    consumed the full display width, hiding the url that does."""
    rows = [
        _Row(
            status_code=401,
            error_message=(
                "Client error '401 Unauthorized' for url "
                "'https://api.respond.io/v2/contact/id:55555/message'\n"
                "For more information check: "
                "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401"
            ),
            count=428,
        )
    ]
    shown = top_failures(rows)[0].sample_message
    assert shown.endswith("id:55555/message'")
    assert "developer.mozilla.org" not in shown


def test_trimming_never_eats_the_leading_error():
    rows = [_Row(status_code=500, error_message="For more information check: nothing")]
    # Marker at position 0: trimming would blank the row. An ugly message beats
    # a fault that renders as an empty line you cannot act on.
    assert top_failures(rows)[0].sample_message == "For more information check: nothing"


# --------------------------------------------------------------------------- #
# filter_text — the substring that selects the whole group in the log list     #
# --------------------------------------------------------------------------- #
_RESPOND_401 = (
    "Client error '401 Unauthorized' for url "
    "'https://api.respond.io/v2/contact/id:55555/message'"
)
# Same channel, same code, same opening prose — different endpoint. This is the
# real pair that exposed the single-term bug.
_RESPOND_401_OTHER_ENDPOINT = (
    "Client error '401 Unauthorized' for url "
    "'https://api.respond.io/v2/contact/id:55555/conversation/status'"
)


def test_filter_terms_exclude_volatile_tokens():
    """The sample message embeds a contact id. Filtering the log list on it would
    return the ONE row it came from, not the 428 rows the count refers to."""
    terms = top_failures([_Row(status_code=401, error_message=_RESPOND_401, count=428)])[0].filter_terms
    assert terms
    assert not any("55555" in t for t in terms)


def test_filter_terms_are_literal_substrings_of_the_original():
    """They are fed to a SQL LIKE, so each must appear verbatim in every row of
    the group — a normalised form with `<id>` placeholders would match nothing."""
    terms = top_failures([_Row(status_code=403, error_message=_RESPOND_401)])[0].filter_terms
    for t in terms:
        assert t in _RESPOND_401


def test_filter_terms_separate_two_faults_sharing_a_long_prefix():
    """The regression this list exists for.

    The longest single stable run of the /message fault stops at the url version
    digit ("…api.respond.io/v"), which is ALSO a prefix of the /conversation/status
    fault. Filtering on that one run returned 433 rows for a group of 428. The
    full term set must be able to tell them apart.
    """
    a = top_failures([_Row(status_code=401, error_message=_RESPOND_401)])[0].filter_terms
    b = top_failures([_Row(status_code=401, error_message=_RESPOND_401_OTHER_ENDPOINT)])[0].filter_terms

    # AND-ing a's terms must not match b's message, and vice versa.
    assert not all(t in _RESPOND_401_OTHER_ENDPOINT for t in a)
    assert not all(t in _RESPOND_401 for t in b)


def test_filter_terms_keep_the_long_descriptive_run():
    rows = [
        _Row(
            status_code=None,
            error_message=(
                "24h window closed and template send skipped for use case "
                "'sla_daily_summary': configured template was removed on sync"
            ),
            count=18,
        )
    ]
    terms = top_failures(rows)[0].filter_terms
    assert any("window closed and template send skipped" in t for t in terms)


def test_filter_terms_are_capped():
    """The whole set travels in a URL; an unbounded list would blow it up."""
    message = " and ".join(f"segment{i} number {i}" for i in range(40))
    assert len(top_failures([_Row(status_code=500, error_message=message)])[0].filter_terms) <= 6


def test_filter_terms_empty_when_message_is_all_volatile():
    """A message of nothing but ids has no stable substring. Better to emit
    nothing than a fragment that would over-match unrelated rows."""
    rows = [_Row(status_code=500, error_message="3f2b1c4e-9a1d-4f7e-88aa-1b2c3d4e5f60 404")]
    assert top_failures(rows)[0].filter_terms == []


def test_empty_input_returns_empty():
    assert top_failures([]) == []
