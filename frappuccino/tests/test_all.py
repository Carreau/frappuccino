from frappuccino.tests import old
from frappuccino.tests import new

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
        ("The following signatures differ between versions:",),
        None,
        ("    tests.changed",),
        ("          - tests.changed(a, b, c)",),
        ("          + tests.changed(x, b, c)",),
    ]
    assert actual == expected
