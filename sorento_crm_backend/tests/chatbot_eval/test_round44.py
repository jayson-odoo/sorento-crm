"""EVAL-BENCH round 44: a capped list with a more-line, and an honest "not recorded" line, on the spec slice.

Owner (19 Oct, card r43; crew a7418687): "Correct, but we shouldn't show all la, should show a cap with the ability to see more" and, on
a material-grade ask, "Yeah" to "grade is not on record for these gratings". Synthetic rows only.
  1. the expected set is larger than a page (`answer.SET_LIST_MAX`, 50): a reply listing a page drawn from it that ends with the
     more-line (`Reply "more" to see the next N.`, composers/sets.py, and its ms / zh forms) passes; a reply listing more than a page fails
  2. a "*<key>:* not recorded for ..." line for the gold's own spec key is the honest none of a none-on-record spec gold, and the
     grounding of its spec words is met when the line names every one of the gold's keys
"""
from __future__ import annotations

from scripts.chatbot_eval.targets import grade_turn
from tests.chatbot_eval.test_targets import item
from tests.chatbot_eval.test_targets_v2 import row2

CLS = {"key": "class", "value": "Water Closet"}
PT = {"key": "trap_type", "value": "p_trap"}
EXPECTED = [f"SRTP{n:03d}" for n in range(1, 61)]   # 60 expected, more than one page of 50
ENTS = [{"hint": "category", "raw": "water closet", "canonical_code": "water closet"},
        {"hint": "specification", "spec_key": "trap_type", "spec_value": "p_trap", "raw": "p trap"}]
MORE = '\nReply "more" to see the next 10.'


def _row(reply):
    return row2(message="which toilets have p trap stock", reply=reply, verdict={"entities": ENTS, "reference_positions": []})


def _check(reply, name="capped_list", **gold):
    g = {"spec": [PT, CLS], "spec_products": EXPECTED, **gold}
    res = grade_turn(_row(reply), item("spec", **g))
    return res["checks"].get(name, "absent"), res


def _list(codes):
    return "\n".join(f"{i}. *Product Code:* {c}" for i, c in enumerate(codes, 1))


def test_red_a_a_reply_over_the_page_cap_fails():
    state, res = _check(_list(EXPECTED))
    assert state is False and res["passed"] is False, (state, res["checks"])


def test_red_b_a_capped_page_from_the_set_with_the_more_line_passes():
    state, res = _check(_list(EXPECTED[:50]) + MORE)
    assert state is True and res["passed"] is True, (state, res["checks"])


def test_red_c_the_page_cap_is_the_bots_own_fifty():
    assert _check(_list(EXPECTED[:51]))[0] is False
    assert _check(_list(EXPECTED[:50]) + MORE)[0] is True


def test_red_d_the_translated_more_lines_pass_too():
    for line in ('\nBalas "more" untuk lihat 10 seterusnya.', '\n回复 "more" 查看接下来的 10 个。',
                 '\nReply “more” to see the next 10.', '\nBalas “more” untuk lihat 10 seterusnya.'):
        assert _check(_list(EXPECTED[:50]) + line)[0] is True, line


def test_red_e_the_word_more_alone_is_no_more_line():
    assert _check(_list(EXPECTED[:20]) + "\nThere is more stock coming.")[0] is None


def test_guard_f_a_set_that_fits_one_page_is_not_judged():
    assert _check(_list(EXPECTED[:3]), spec_products=EXPECTED[:3])[0] == "absent"
    assert _check(_list(EXPECTED[:50]), spec_products=EXPECTED[:50])[0] == "absent"


def test_red_g_a_page_without_the_more_line_is_not_a_failure_here():
    assert _check(_list(EXPECTED[:20]))[0] is None


def test_red_h_a_page_that_is_not_drawn_from_the_set_is_left_to_the_other_checks():
    assert _check(_list(["XOTH001", *EXPECTED[:10]]) + MORE)[0] is None


def test_guard_i_a_none_on_record_gold_is_not_judged_by_the_page_check():
    assert _check(_list(EXPECTED), none_on_record=True)[0] == "absent"


def test_guard_j_a_reply_with_no_product_is_not_judged():
    assert _check("Sorry, nothing matched.")[0] == "absent"


def test_red_k_more_than_a_page_fails_whatever_the_expected_set_size():
    codes = [f"SRTQ{n:03d}" for n in range(1, 92)]
    assert _check(_list(codes), spec_products=[])[0] is False
    assert _check(_list(codes), spec_products=EXPECTED[:5])[0] is False


GRADE = {"key": "steel_grade", "value": "201"}
GRADE2 = {"key": "steel_grade", "value": "304"}
LINE = "1. *Product Code:* SRTG100\n\n*steel_grade:* not recorded for SRTG100, SRTG100-BP"


def _none(reply, spec=(GRADE, GRADE2)):
    res = grade_turn(_row(reply), item("spec", spec=list(spec), none_on_record=True))
    return res["checks"], res


def test_red_l_a_not_recorded_line_for_the_asked_attribute_is_the_honest_none():
    assert _none(LINE)[0]["none_on_record"] is True


def test_red_m_the_registry_label_form_of_the_line_reads_too():
    assert _none("1. *Product Code:* SRTG100\n\n*Steel grade:* not recorded for SRTG100 (+2 more)")[0]["none_on_record"] is True


def test_red_n_the_line_naming_every_gold_key_meets_the_spec_words():
    checks, res = _none(LINE)
    assert checks["spec_set"] is True and res["passed"] is True, checks


def test_guard_o_a_line_for_another_attribute_is_no_honest_none_and_grounds_nothing():
    checks, res = _none("1. *Product Code:* SRTG100\n\n*finish:* not recorded for SRTG100")
    assert checks["none_on_record"] is False and checks["spec_set"] is False and res["passed"] is False, checks


def test_red_p_a_line_naming_only_one_of_two_gold_keys_does_not_meet_the_spec_words():
    checks, _ = _none("1. *Product Code:* SRTG100\n\n*steel_grade:* not recorded for SRTG100",
                      spec=(GRADE, {"key": "finish", "value": "chrome"}))
    assert checks["none_on_record"] is True and checks["spec_set"] is False, checks


def test_guard_q_products_with_no_such_line_stay_no_honest_none():
    checks, _ = _none("1. *Product Code:* SRTG100")
    assert checks["none_on_record"] is False and checks["spec_set"] is False, checks


def _stock_page(codes):
    block = "{i}. *Product Code:* {c}\n*Material:* SUS304\n*DC1-SMC:* 0\n*WH3-IB:* 4"
    return "\n".join(block.format(i=i, c=c) for i, c in enumerate(codes, 1))


def test_red_r_a_fifty_product_stock_page_with_warehouse_rows_and_the_more_line_passes():
    state, res = _check(_stock_page(EXPECTED[:50]) + MORE)
    assert state is True and res["passed"] is True, (state, res["checks"])


def test_red_s_a_set_of_forty_nine_listed_whole_with_warehouse_rows_is_not_a_dump():
    assert _check(_stock_page(EXPECTED[:49]), spec_products=EXPECTED[:49])[0] == "absent"


def test_guard_t_sixty_products_with_warehouse_rows_are_still_a_dump():
    assert _check(_stock_page(EXPECTED))[0] is False


def test_guard_u_a_bullet_or_plain_code_row_is_a_product_row():
    rows = "\n".join(f"- {c} 4 pcs" for c in EXPECTED[:50]) + MORE
    assert _check(rows)[0] is True
    assert _check("\n".join(f"{c} 4 pcs" for c in EXPECTED))[0] is False


def test_red_v_a_gold_value_shown_on_one_product_refuses_the_honest_none():
    reply = ("1. *Product Code:* SRTG100\n*Steel grade:* 201\n2. *Product Code:* SRTG200\n\n"
             "*steel_grade:* not recorded for SRTG200")
    checks, res = _none(reply)
    assert checks["none_on_record"] is False and checks["spec_set"] is False and res["passed"] is False, checks


def test_guard_w_a_line_for_another_value_of_the_key_is_no_refusal_to_a_value_not_asked():
    reply = ("1. *Product Code:* SRTG100\n*Steel grade:* 316\n\n*steel_grade:* not recorded for SRTG200")
    assert _none(reply)[0]["none_on_record"] is True


def _rows(codes, label):
    return "\n".join(f"{i}. *{label}:* {c}\n*DC1-SMC:* 0" for i, c in enumerate(codes, 1))


MS_MORE = '\nBalas "more" untuk lihat 10 seterusnya.'
ZH_MORE = '\n回复 "more" 查看接下来的 10 个。'


def test_red_x_a_fifty_row_malay_page_with_its_more_line_passes():
    assert _check(_rows(EXPECTED[:50], "Kod Produk") + MS_MORE)[0] is True


def test_red_y_a_fifty_row_chinese_page_with_its_more_line_passes():
    assert _check(_rows(EXPECTED[:50], "产品代码") + ZH_MORE)[0] is True


def test_red_z_a_sixty_row_malay_or_chinese_dump_fails():
    assert _check(_rows(EXPECTED, "Kod Produk"))[0] is False
    assert _check(_rows(EXPECTED, "产品代码"))[0] is False


def test_red_aa_one_comma_line_of_sixty_codes_is_a_dump():
    assert _check(", ".join(EXPECTED))[0] is False


def test_guard_ab_a_comma_line_of_three_codes_is_not_a_dump():
    assert _check("Water closets with stock: " + ", ".join(EXPECTED[:3]))[0] is not False


def _fifty_nine_rows_and(line):
    return _rows(EXPECTED[:48], "Product Code") + "\n" + line


def test_red_ac_a_spec_value_line_with_code_shaped_values_is_no_comma_run():
    page = _fifty_nine_rows_and("*Material:* SUS304, SUS316")
    assert _check(page + MORE)[0] is True
    assert _check(page, spec_products=EXPECTED[:48])[0] == "absent"


def test_red_ad_a_warehouse_sentence_is_no_comma_run():
    page = _fifty_nine_rows_and("Stock sits at DC1-SMC, WH3-IB.")
    assert _check(page + MORE)[0] is True
    assert _check(_rows(EXPECTED[:49], "Product Code") + "\nStock sits at DC1-SMC, WH3-IB.", spec_products=EXPECTED[:49])[0] == "absent"


def test_guard_ae_a_comma_run_after_a_product_label_or_not_recorded_for_still_counts():
    for head in ("*Product:* ", "\u2022 product: ", "*Product Code:* ", "*Kod Produk:* ", "*\u4ea7\u54c1\u4ee3\u7801:* "):
        assert _check(head + ", ".join(EXPECTED))[0] is False, head
    assert _check("*steel_grade:* not recorded for " + ", ".join(EXPECTED))[0] is False
