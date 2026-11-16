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
