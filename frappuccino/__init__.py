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
positional parameters can be use a keyword arguments. That is to say one of your customer may use:

```python
read(name='dump.csv')
```

Hence changing the _name_ of the positional parameter from `name` to
`name_or_buffer` is a change of API. There are a number of details like this one
where you _may_ end up breaking API without realizing. It's hard to keep track
of this when working on dev branches, unit test may not catch all of that.
Frappuccino is there to help.
"""

__version__ = '0.0.2'

import importlib
import inspect
import types
import json
import sys
import re

from .visitor import BaseVisitor
from .logging import logger

hexd = re.compile('0x[0-9a-f]+')


def hexuniformify(s: str) -> str:
    """
    Uniforming hex addresses to `0xffffff` to avoid difference between rerun.

    Difference  may be due to object id varying in reprs.
    """
    return hexd.sub('0xffffff', s)


# likely unused code used for testing at some point


def foo():
    pass


def sigfd(data):
    """
    Try to convert a dump to a string human readable
    """
    from inspect import Parameter,Signature
    from copy import copy
    prms = []
    for v in data.values():
        v = copy(v)
        kind = getattr(Parameter, v.pop('kind'))
        prms.append(Parameter(kind=kind, **v))
    return Signature(prms)
# sigfd(data)


def signature_from_text(text):
    loc = {}
    glob = {}
    try:
        exec(
            compile('from typing import *\ndef function%s:pass' % text, '<fakefile>', 'exec'), glob,
            loc
        )
        sig = inspect.signature(loc['function'])
    except Exception as e:
        print(' failed:>>> def function%s:pass' % text)
        return inspect.signature(foo)
        raise
    return sig


####


def parameter_dump(p):
    """
    Given a parameter (from inspect signature), dump to to json
    """
    # TODO: mapping of kind  and drop default if inspect empty + annotations.
    return {'kind': str(p.kind), 'name': p.name, 'default': hexuniformify(str(p.default))}


def sig_dump(sig):
    """
    Given a signature (from inspect signature), dump ti to json
    """
    return {k: parameter_dump(v) for k, v in sig.parameters.items()}


def fully_qualified(obj: object) -> str:
    """
    (try to) return the fully qualified name of an object
    """
    if obj is types.FunctionType:  # noqa
        return '%s.%s' % (obj.__module__, obj.__qualname__)
    else:
        return '%s.%s' % (obj.__class__.__module__, obj.__class__.__name__)


class Visitor(BaseVisitor):

    def visit_metaclass_instance(self, meta_instance):
        return self.visit_type(meta_instance)
        pass

    def visit_unknown(self, unknown):
        self.rejected.append(unknown)

        self.logger.debug('Unknown: ========')
        self.logger.debug('Unknown: No clue what to do with %s', unknown)
        self.logger.debug('Unknown: isinstance(node, object) %s', isinstance(unknown, object))
        self.logger.debug('Unknown: isinstance(node, type) %s', isinstance(unknown, type))
        self.logger.debug('Unknown: type(node) %s', type(unknown))
        if type(unknown) is type:
            self.logger.debug('Unknown: issubclass(unknown, type) %s', issubclass(unknown, type))
        self.logger.debug(
            'Unknown: issubclass(type(unknown), type) %s %s',
            issubclass(type(unknown), type), type(unknown)
        )
        self.logger.debug('Unknown: type(unknown) is type :  %s', type(unknown) is type)
        self.logger.debug(
            'Unknown: hasattr(unknown, "__call__"):  %s', hasattr(unknown, "__call__")
        )
        self.logger.debug('Unknown: ========')

    def visit_method_descriptor(self, meth):
        pass

    def visit_builtin_function_or_method(self, b):
        pass

    def visit_method(self, b):
        return self.visit_function(b)

    def visit_function(self, function):
        name = function.__module__
        #else:
        #    name = '%s.%s' % (function.__class__.__module__, function.__class__.__name__)
        fullqual = '{}.{}'.format(name, function.__qualname__)
        #if 'leading_empty_lines' in function.__qualname__:
        #    raise ValueError(fullqual, function.__module__, type(function) )
        # try:
        sig = hexuniformify(str(inspect.signature(function)))
        # except ValueError:
        #    return
        self.logger.debug('    visit_function {f}{s}'.format(f=fullqual, s=sig))
        self.collected.add(fullqual)
        self.spec[fullqual] = {
            'type': 'function',
            'signature': sig_dump(inspect.signature(function))
        }
        self._consistent(fullqual, function)
        return fullqual

    def visit_instance(self, instance):
        self.rejected.append(instance)
        self.logger.debug('    visit_instance %s', instance)
        try:
            return str(instance)
        except:
            pass

    def visit_type(self, type_):
        local_key = type_.__module__ + '.' + type_.__qualname__
        items = {}
        self.logger.debug('Class %s' % type_.__module__ + '.' + type_.__qualname__)
        for k in sorted(dir(type_)):
            if not k.startswith('_'):
                items[k] = self.visit(getattr(type_, k))
        items = {k: v for k, v in items.items() if v}
        self.spec[local_key] = {'type': 'type', 'items': items}
        self.collected.add(local_key)
        return local_key

    def visit_module(self, module):
        self.logger.debug('Module %s' % module)
        if not module.__name__.startswith(self.name):
            self.logger.debug(
                'out of scope %s vs %s : %s' %
                (module.__name__, self.name, module.__name__.startswith(self.name))
            )
            return None
        for k in dir(module):
            if k.startswith('_') and not (k.startswith('__') and k.endswith('__')):
                self.logger.debug(
                    '     visit_module: skipping private attribute: %s.%s' % (module.__name__, k)
                )
                continue
            else:
                self.logger.debug(
                    '     visit_module: visiting public attribute; %s.%s' % (module.__name__, k)
                )
                self.visit(getattr(module, k))


def param_compare(old, new):
    if old is None:
        print('     New paramters', repr(new))
        return
    print('    ', old, '!=', new)


def params_compare(old_ps, new_ps):
    try:
        from itertools import zip_longest
        for (o, ov), (n, nv) in zip_longest(old_ps.items(), new_ps.items(), fillvalue=(None, None)):
            if o == n and ov == nv:
                continue
            param_compare(ov, nv)
    except:
        import ipdb
        ipdb.set_trace()


def visit_modules(rootname: str, modules):
    """
    visit given modules and return a tree visitor that have visited the given modules.

    Will only recursively visit modules with fully qualified names starting with
    `rootname`. It is possible to pass several modules to inspect as python does
    not always expose submodules, as they need to be explicitly imported. For
    example, `matplotlib` does not expose `matplotlib.finance`, so a user would need to do 

    `visit_module('matplotlib', [matplotlib, matplotlib.finance]` after
    explicitly having imported both.

    Another example would be namespace packages.

    This is not made to explore at one multiple top level modules. (Maybe we
    should allow that for things that re-expose other projects but that's a
    question for another time.
    """
    tree_visitor = Visitor(rootname.split('.')[0], logger=logger)
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
            except (ImportError, RuntimeError, AttributeError) as e:
                skipped.append(module_name)
                continue
        tree_visitor.visit(module)

    return skipped, tree_visitor


def compare(old_spec, new_spec, *, tree_visitor):
    """
    Given an old_specification and a new_specification print differences.

    Todo:  yield better structured informations

    """
    old_keys = set(old_spec.keys())
    common_keys = new_spec.intersection(old_keys)
    removed_keys = old_keys.difference(new_spec)
    new_keys = new_spec.difference(old_keys)
    if new_keys:
        yield ("The following items are new:", )
        for k in new_keys:
            yield '    '+k,
        yield
    if removed_keys:
        yield (
            "The following items have been removed, (or moved to super-class)",
        )
        for k in removed_keys:
            yield ('    '+k,)
        yield

    # Todo, print that only if there are differences.
    yield ("The following signature differ between versions:", )
    for key in common_keys:
        # if isinstance(old_spec[key], str):
        #     from_dump = hexuniformify(old_spec[key])
        #     current_spec = hexuniformify(tree_visitor.spec[key])
        # else:
        from_dump = old_spec[key]
        current_spec = tree_visitor.spec[key]

        if from_dump != current_spec:

            if current_spec['type'] == 'type':  # Classes / Module / Function
                current_spec = current_spec['items']
                from_dump = from_dump['items']
                removed = [k for k in from_dump if k not in current_spec]
                if not removed:
                    continue
                yield
                yield ("    %s" % (key), )
                new = [k for k in current_spec if k not in from_dump]
                if new:
                    for n in new:
                        yield ('              new:', n)
                removed = [k for k in from_dump if k not in current_spec]
                if removed:
                    for r in removed:
                        yield ('              removed:', r)
            elif current_spec['type'] == 'function':
                from_dump = from_dump['signature']
                current_spec = current_spec['signature']
                yield
                yield ("    %s" % (key), )
                yield ("          - %s%s" % (key, sigfd(from_dump)), )
                yield ("          + %s%s" % (key, sigfd(current_spec)), )
                #params_compare(from_dump, current_spec)
            else:
                yield ('unknown node:', current_spec)


def main():
    import argparse
    from textwrap import dedent
    from argparse import RawTextHelpFormatter

    parser = argparse.ArgumentParser(
        description=dedent("""
            An easy way to be confident you haven't broken API contract since a
            previous version, or see what changes have been made."""),
        formatter_class=RawTextHelpFormatter,
        epilog=dedent("""

            Example:
                                                                       
                $ pip install 'ipython==5.1.0'
                $ frappuccino IPython --save IPython-5.1.0.json

                $ pip install 'ipython==6.0.0'

                $ frappuccino IPython --compare IPython-5.1.0.json
                                                                 
            ... list of API changes found + non zero exit code if incompatible ...

            """),
        allow_abbrev=False
    )
    parser.add_argument(
        'modules', metavar='modules', type=str, nargs='+', help='root modules and submodules'
    )
    parser.add_argument('--save', action='store', help='file to dump API to', metavar='<file>')
    parser.add_argument(
        '--compare', action='store', help='file with dump API to compare to', metavar='<file>'
    )
    parser.add_argument('--debug', action='store_true')

    # TODO add stdin/stdout options for spec.

    options = parser.parse_args()

    if options.save and options.compare:
        parser.print_help()
        sys.exit('options `--save` and `--compare` are exclusive')

    if options.debug:
        logger.setLevel('DEBUG')

    rootname = options.modules[0]
    tree_visitor = Visitor(rootname.split('.')[0], logger=logger)

    skipped, tree_visitor = visit_modules(rootname, options.modules)
    if skipped:
        print('skipped modules :', ','.join(skipped))

    print(
        "Collected:",
        len(tree_visitor.collected), "Visited:",
        len(tree_visitor.visited), "Rejected:", len(tree_visitor.rejected)
    )

    if options.save:
        with open(options.save, 'w') as f:
            f.write(json.dumps(tree_visitor.spec, indent=2))
    if options.compare:
        with open(options.compare, 'r') as f:
            loaded = json.loads(f.read())

        skeys = set(tree_visitor.spec.keys())
        for c in compare(loaded, skeys, tree_visitor=tree_visitor):
            if c is None:
                print()
            else:
                print(*c)


if __name__ == '__main__':
    main()
