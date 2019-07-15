from frappuccino.tests import old
from frappuccino.tests import new
from inspect import signature

import json

from frappuccino import visit_modules, compare


def fix_spec(spec, old: str, new: str):
    return {k.replace(old, new): v for k, v in spec.items()}


def test_old_new():
    skipped_o, old_spec_visitor = visit_modules("", [old])
    skipped_n, new_spec_visitor = visit_modules("", [new])

    assert skipped_o == []
    assert skipped_n == []

    old_spec = fix_spec(old_spec_visitor.spec, "frappuccino.tests.old", "tests")
    new_spec = fix_spec(new_spec_visitor.spec, "frappuccino.tests.new", "tests")

    actual = list(compare(old_spec, spec=new_spec))
    assert json.dumps(old_spec) != "{}"
    expected = [
        set(),
        set(),
        [
            ["tests.Example", None, "x"],
            ["tests.Example", None, "y"],
            ["tests.Example", "a", None],
            ["tests.Example", "b", None],
            [
                "tests.changed",
                signature(lambda a, b, c: None),
                signature(lambda x, b, c: None),
            ],
            [
                "tests.other",
                signature(lambda a, b, c: None),
                signature(lambda x, b, c: None),
            ],
        ],
    ]
    assert expected == actual
