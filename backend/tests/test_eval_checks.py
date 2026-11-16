from evals.run_chat import check


def test_passing_answer_has_no_reasons() -> None:
    case = {"language": "en", "must_include_any": ["Al-Quds"], "must_not_include": ["GPA was"]}

    assert check(case, "He studied Information Technology at Al-Quds University.") == []


def test_each_failed_check_is_reported() -> None:
    case = {"language": "ar", "must_include_any": ["Nawa"], "must_not_include": ["$"]}

    reasons = check(case, "It costs $5.")

    assert reasons == [
        "language is not ar",
        "missing all of must_include_any",
        "contains forbidden '$'",
    ]


def test_arabic_matching_ignores_diacritics_and_case() -> None:
    case = {"language": "ar", "must_include_any": ["مستقل", "linkedin"]}

    assert check(case, "إنه مشروعٌ أكاديميٌّ مستقلّ عن البنك.") == []
    assert check({"must_include_any": ["linkedin"]}, "Find him on LINKEDIN.") == []


def test_empty_answer_fails() -> None:
    assert check({"language": "en"}, "  ") == ["empty answer"]


def test_unicode_hyphens_and_spaces_match_plain_ones() -> None:
    # gpt-oss writes "Al‑Quds" with U+2011 and puts U+202F before URLs.
    assert check({"must_include_any": ["Al-Quds"]}, "He studied at Al\u2011Quds University.") == []


def test_markdown_in_an_answer_fails() -> None:
    assert check({}, "His best work is the **AI Developer Assistant**.") == ["uses markdown"]
    assert check({}, "Highlights:\n- one\n- two") == ["uses markdown"]
    assert check({}, "He wrote it in C++ and Python - a fast engine.") == []


def test_must_include_all_reports_each_missing_item() -> None:
    case = {"must_include_all": ["Nawa", "Momentum", "Smart System"]}

    assert check(case, "He built Nawa and Momentum.") == ["missing Smart System"]
    assert check(case, "Nawa, Momentum and Smart System.") == []


def test_praise_words_fail_in_both_languages() -> None:
    assert check({}, "He has a deep understanding of AI.") == ["praise 'deep understanding'"]
    assert check({}, "لديه شغف كبير بالذكاء الاصطناعي.") == ["praise 'شغف'"]
    assert check({}, "He built Nawa from scratch in C++.") == []


def test_known_arabic_mistakes_fail() -> None:
    assert check({}, "بناها عبد الله بنفسه.") == ["Arabic mistake 'عبد الله'"]
    assert check({}, "المنصة لم تُبنى للبنك.") == ["Arabic mistake 'لم تُبنى'"]
    assert check({}, "بناها عبدالله ذويب بنفسه، ولم تُبنَ للبنك.") == []


def test_latin_glued_to_arabic_fails() -> None:
    [reason] = check({}, "ولا يستخدمها أو ي endorsه.")
    assert reason.startswith("Latin glued to Arabic") and "endorsه" in reason
    assert check({}, "استخدم وReact في المشروع.")[0].startswith("Latin glued to Arabic")
    assert check({}, "استخدم Python و React عبر LinkedIn.") == []
    # Arabic punctuation right after an English word is correct, not "glued".
    assert check({}, "في مشروع AI Developer Assistant، حقق نتائج؛ هل تعرف MCP؟") == []
    assert check({}, "يعتمد بـMCP")[0].startswith("Latin glued to Arabic")  # tatweel still counts


def test_urls_fail_because_answers_are_spoken() -> None:
    assert check({}, "See https://github.com/x for details.") == ["reads out a URL"]
    assert check({}, "You can find him on GitHub and LinkedIn.") == []


def test_template_placeholders_fail() -> None:
    # gpt-oss-20b once copied a prompt template verbatim.
    answer = "بنى عبدالله ذويب مشروع <project name> بنفسه."
    assert check({}, answer) == ["template placeholder '<project name>'"]
    assert check({}, "Recall@5 is above 0.9 and latency < 10 ms.") == []
