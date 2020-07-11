"""
Frappuccino
===========

Freeze your API.

Frappucino allows you during development to make sure you haven't broken API. By
first taking an imprint of your API, at one point in time and then compare it to
the current project state it can warn you whether you have introduced
incompatible changes, and list theses.

You should (of course) integrate it in you CI to make sure you don't
inadvertently break things.

Example:

```python
# old function
def read(name, *, options=None):
    with open(name. 'rb') as f:
        return process(data)

# new function
def read(name_or_buffer, *, options=None):
    if isinstance(name, str):
        with open(name, 'rb') as f:
            data = f.read()
    else:
        data = name_or_buffer.read()
    return process(data)
```

There is a subtle breakage of API in the above, as you may not remember
positional parameters can be use a keyword arguments. That is to say one of
your customer may use:

```python
read(name='dump.csv')
```

Hence changing the _name_ of the positional parameter from `name` to
`name_or_buffer` is a change of API. There are a number of details like this one
where you _may_ end up breaking API without realizing. It's hard to keep track
of this when working on dev branches, unit test may not catch all of that.
Frappuccino is there to help.
"""

__version__ = "0.0.8"

import argparse
import importlib
import inspect
import json
import re
import sys
import types
from argparse import RawTextHelpFormatter
from collections import defaultdict
from copy import copy
from inspect import Parameter, Signature
from pathlib import Path
from textwrap import dedent

import pytoml

from .logging import logger
from .visitor import Visitor, hexuniformify, sig_dump


def format_signature_from_dump(data):
    """
    Try to convert a dump to a string human readable
    """
    prms = []
    for k, v in data:
        v = copy(v)
        default = v.pop("default")
        kind = getattr(Parameter, v.pop("kind"))
        name = v.pop("name")
        annotation = v.get("annotation", inspect._empty)
        if default == "<class 'inspect._empty'>":
            default = inspect._empty
        if annotation == "<class 'inspect._empty'>":
            annotation = inspect._empty
        try:
            prms.append(
                Parameter(name=name, default=default, annotation=annotation, kind=kind)
            )
        except Exception:
            raise
            return "(<couldn't compute signature>)"
    return Signature(prms)


def deserialize_spec(compact_spec):
    compact_spec = json.loads(compact_spec)
    expanded_spec = dict()
    for type_, container in compact_spec.items():
        for k, v in container.items():
            if type_ == "function":
                if isinstance(v, str):
                    d = {"inf": float("inf")}
                    try:
                        exec(f"def f{v}:pass", d)
                        sig = sig_dump(inspect.signature(d["f"]))
                    except:
                        print("V is ", repr(v))
                else:
                    sig = v
                assert k not in expanded_spec
                expanded_spec[k] = {"signature": sig}
            else:
                assert k not in expanded_spec
                expanded_spec[k] = v

            expanded_spec[k]["type"] = type_
    return expanded_spec


def serialize_spec(expanded_spec):
    """Serialise an API spec.

    1) swap key order:
        from [{type:...}, {type:...}, {type:...}]
        to {'function': [{...}], 'module':[...]}
    highly decrease redundancy on disk and make it more human friendly.


    """
    compact_spec = defaultdict(lambda: {})
    for key, value in expanded_spec.items():
        type_ = value["type"]
        store = {k: v for k, v in value.items() if k != "type"}
        if type_ == "function":
            store = _serialise_function_signature(store["signature"])
        compact_spec[type_][key] = store
    return json.dumps(compact_spec, indent=2)


def _serialise_function_signature(function_signature):
    """
    For _some_ signature, we can serialise it in a more human readable for.

    In particular if there are no Pos-Onlyarguments, we can dump-it use normal python syntax.
    Which we can parse back.
    """
    ps = []
    for argname, parameter_info in function_signature:
        if parameter_info["kind"] == "POSITIONAL_ONLY":
            return function_signature
        parameter_info = copy(parameter_info)
        default = parameter_info.pop("default")
        kind = getattr(Parameter, parameter_info.pop("kind"))
        name = parameter_info.pop("name")
        annotation = parameter_info.get("annotation", inspect._empty)
        if default == "<class 'inspect._empty'>":
            default = inspect._empty
        if annotation == "<class 'inspect._empty'>":
            annotation = inspect._empty
        ps.append(
            Parameter(name=name, default=default, annotation=annotation, kind=kind)
        )
    return str(Signature(ps))


def param_compare(old, new):
    if old is None:
        print("     New paramters", repr(new))
        return
    print(">>    ", old, "!=", new)
    for k in ["name", "kind", "default", "annotation"]:
        o, n = old.get(k, inspect._empty), new.get(k, inspect._empty)
        if o != n:
            print(">>", k, o, n)


def params_compare(old_ps, new_ps):
    try:
        from itertools import zip_longest

        for (o, ov), (n, nv) in zip_longest(old_ps, new_ps, fillvalue=(None, None)):
            if o == n and ov == nv:
                continue
            param_compare(ov, nv)
    except Exception:
        raise


def visit_modules(rootname: str, modules):
    """
    visit given modules and return a tree visitor that have visited the given modules.

    Will only recursively visit modules with fully qualified names starting with
    `rootname`. It is possible to pass several modules to inspect as python does
    not always expose submodules, as they need to be explicitly imported. For
    example, `matplotlib` does not expose `matplotlib.finance`, so a user would
    need to do

    `visit_module('matplotlib', [matplotlib, matplotlib.finance]` after
    explicitly having imported both.

    Another example would be namespace packages.

    This is not made to explore multiple top level modules. (Maybe we
    should allow that for things that re-expose other projects but that's a
    question for another time.
    """
    tree_visitor = Visitor(rootname.split(".")[0], logger=logger)
    skipped = []
    for module_name in modules:
        # Here we allow also ModuleTypes for easy testing, figure out a clean
        # way with stable types. Likely move the requirement to import things
        # one more level up, then we can also remove the need for catching
        # import,runtime and attribute errors and push it to the caller.
        if isinstance(module_name, types.ModuleType):
            module = module_name
        else:
            try:
                module = importlib.import_module(module_name)
            except (ImportError, RuntimeError, AttributeError):
                skipped.append(module_name)
                raise
                continue
        tree_visitor.visit(module)

    return skipped, tree_visitor


def _sorted_list(it):

    return list(sorted(it, key=str))


def compare(old_spec, *, spec):
    """
    Given an old_specification and a new_specification print differences.

    Todo:  yield better structured informations

    """
    new_spec = spec
    new_spec_keys = set(new_spec.keys())
    old_spec_keys = set(old_spec.keys())

    _common_keys = new_spec_keys.intersection(old_spec_keys)
    _removed_keys = old_spec_keys.difference(new_spec_keys)
    _added_keys: set = new_spec_keys.difference(old_spec_keys)

    # Todo, print that only if there are differences.
    changed_keys = []
    for key in sorted(_common_keys):
        from_dump = old_spec[key]
        current_spec = new_spec[key]

        if from_dump != current_spec:

            if current_spec["type"] == "type":  # Classes / Module / Function
                current_spec_item = current_spec["items"]
                try:
                    from_dump = from_dump["items"]
                except KeyError:
                    continue
                new = [k for k in current_spec_item if k not in from_dump]
                if new:
                    for n in new:
                        changed_keys.append([key, None, n])
                removed = [k for k in from_dump if k not in current_spec_item]
                if removed:
                    for r in removed:
                        changed_keys.append([key, r, None])
            elif current_spec["type"] == "function":
                from_dump = from_dump["signature"]
                current_spec_item = current_spec["signature"]
                changed_keys.append(
                    [
                        key,
                        format_signature_from_dump(from_dump),
                        format_signature_from_dump(current_spec_item),
                    ]
                )
            elif current_spec["type"] == "module_item":
                pass  # not implemented.
            else:
                raise ValueError(current_spec["type"])
    new_keys = []
    for k in _added_keys:
        current_spec = new_spec[k]
        if current_spec["type"] == "function":
            new_keys.append(
                [k, str(format_signature_from_dump(current_spec["signature"]))]
            )
        else:
            new_keys.append([k, ""])

    return (
        _sorted_list(new_keys),
        _sorted_list(_removed_keys),
        _sorted_list(changed_keys),
    )


def main():
    parser = argparse.ArgumentParser(
        description=dedent(
            """
            An easy way to be confident you haven't broken API contract since a
            previous version, or see what changes have been made."""
        ),
        formatter_class=RawTextHelpFormatter,
        epilog=dedent(
            f"""
            Frappuccino version {__version__}

            Example:

                $ pip install 'ipython==5.1.0'
                $ frappuccino IPython --save IPython-5.1.0.json

                $ pip install 'ipython==6.0.0'

                $ frappuccino IPython --compare IPython-5.1.0.json

            ... list of API changes found + non zero exit code if incompatible ...

            When submodules need to be explicitly crawled, list them explicitely:

                 $ frappuccino astropy astropy.timeseries .... --options.

            """
        ),
        allow_abbrev=False,
    )
    parser.add_argument(
        "modules",
        metavar="modules",
        type=str,
        nargs="*",
        help="root modules and submodules",
    )
    parser.add_argument(
        "--save", action="store", help="file to dump API to", metavar="<file>"
    )
    parser.add_argument(
        "--version", action="store_true", help="print version number on exit."
    )
    parser.add_argument(
        "--compare",
        action="store",
        help="file with dump API to compare to",
        metavar="<file>",
    )
    parser.add_argument("--debug", action="store_true")

    # TODO add stdin/stdout options for spec.

    options = parser.parse_args()

    conffile = Path("pyproject.toml")
    conf = {}
    if conffile.exists():
        with conffile.open() as f:
            conf = pytoml.load(f)
        conf = conf.get("tool", {}).get("frappuccino", {})

    if options.version:
        print(__version__)
        sys.exit(0)

    if options.debug:
        logger.setLevel("DEBUG")

    if not options.modules:
        sys.exit("Pass at least one module name")

    rootname = options.modules[0]
    # tree_visitor = Visitor(rootname.split('.')[0], logger=logger)

    skipped, tree_visitor = visit_modules(rootname, options.modules)
    if skipped:
        print("skipped modules :", ",".join(skipped))

    print("Collected (Object founds):", len(tree_visitor.collected))
    print("Visited (don't start with _, not in stdlib...):", len(tree_visitor.visited))
    print(
        "Rejected (Unknown nodes, or instances, don't know what to do with those):",
        len(tree_visitor.rejected),
    )
    print()

    if options.save:
        with open(options.save, "w") as f:
            f.write(serialize_spec(tree_visitor.spec))
    if options.compare:
        with open(options.compare, "r") as f:
            loaded = deserialize_spec(f.read())

        # round trip for testing, and make a deepcopy
        spec = deserialize_spec(serialize_spec(tree_visitor.spec))
        assert spec == tree_visitor.spec

        new_keys, removed_keys, changed_keys = compare(loaded, spec=tree_visitor.spec)
        if new_keys:
            print("The following items are new:")
            for n in new_keys:
                print("    +", n[0] + n[1])
            print()
        if removed_keys:
            print("The following items have been removed (or moved to superclass):")
            for o in removed_keys:
                print("    -", o)
            print()
        if changed_keys:
            print("The following signatures differ between versions:")
            for k, o, n in changed_keys:
                if n is None or o is None:
                    continue
                print()
                print(f"    - {k}{o}")
                print(f"    + {k}{n}")

            print()
            print("The following attribute seem new, but we are not too sure,")
            print(
                "(They might be new inherited attributes, or stuff we don't handle yet)"
            )
            print()
            for k, o, n in changed_keys:
                if o is not None or f"{k}.(n)" in new_keys:
                    continue

                print(f"    + {k}.{n}")

            print()
            print("The following attribute seem to have been removed:")
            print(
                "(They might have been inherited attributes, or stuff we didn't handle then)"
            )
            print()
            for k, o, n in changed_keys:
                if n is not None or f"{k}.{o}" in removed_keys:
                    continue
                print(f"    - {k}.{o}")

        if any([new_keys, removed_keys, changed_keys]):
            sys.exit(1)


if __name__ == "__main__":
    main()
