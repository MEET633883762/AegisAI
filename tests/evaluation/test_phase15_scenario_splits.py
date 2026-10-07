import pytest

from evaluation.experiments.protocol import build_template_holdout_split


def test_template_holdout_split_has_unseen_templates():
    split = build_template_holdout_split(
        ("web_exploit_lateral_exfil", "credential_reuse_known_vuln"),
        ("web_exploit_high_noise",),
        ("credential_reuse_workstation",),
        (1, 2, 7),
    )
    assert {x[0] for x in split.train} == {"web_exploit_lateral_exfil", "credential_reuse_known_vuln"}
    assert {x[0] for x in split.validation} == {"web_exploit_high_noise"}
    assert {x[0] for x in split.test} == {"credential_reuse_workstation"}
    assert not ({x[0] for x in split.train} & {x[0] for x in split.test})


def test_template_holdout_split_rejects_overlap():
    with pytest.raises(ValueError):
        build_template_holdout_split(("a",), ("a",), ("b",), (1,))


def test_template_holdout_split_rejects_empty_group_or_seed_set():
    with pytest.raises(ValueError):
        build_template_holdout_split((), ("b",), ("c",), (1,))
    with pytest.raises(ValueError):
        build_template_holdout_split(("a",), ("b",), ("c",), ())
