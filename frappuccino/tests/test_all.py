from . import old
from . import new

import json

from .. import main, visit_modules, compare


def test_old_new():
    skipped_o, old_spec = visit_modules('', [old])
    skipped_n, new_spec = visit_modules('', [new])

    assert skipped_o == []
    assert skipped_n == []

    skeys = set(new_spec.spec.keys())

    l = list(compare(old_spec.spec, skeys, tree_visitor=new_spec))
    assert json.dumps(old_spec.spec) is not '{}'
    assert l == [
        ('The following signature differ between versions:', ), None,
        ('function> builtins.function.changed', ), ('          builtins.function.changed', )
    ]
