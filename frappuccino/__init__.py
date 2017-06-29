"""
Frappuccino
===========

> Yes there is only one N.

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

__version__ = '0.0.1'


import importlib
import inspect
import types
import json
import re

from pprint import pprint
from types import ModuleType

import logging
logging.basicConfig()
logger = logging.getLogger(__name__)

hexd = re.compile('0x[0-9a-f]+')


def hexuniformify(s: str)->str:
    """
    Uniforming hex addresses to `0xffffff` to avoid difference between rerun.

    Difference  may be due to object id varying in reprs.
    """
    return hexd.sub('0xffffff', s)


### likely unused code used for testing at some point

def foo():
    pass

def signature_from_text(text):
    loc = {}
    glob = {}
    try:
        exec(compile('from typing import *\ndef function%s:pass' %
                     text, '<fakefile>', 'exec'), glob, loc)
        sig = inspect.signature(loc['function'])
    except Exception as e:
        print(' failed:>>> def function%s:pass' % text)
        return inspect.signature(foo)
        raise
    return sig


####



def parameter_dump(p):
    """
    Given a parameter (from inspect signature), dump ti to json
    """
    # TODO: mapping of kind  and drop default if inspect empty + annotations.
    return {'kind': str(p.kind),
            'name': p.name,
            'default': hexuniformify(str(p.default))}


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


class Visitor:

    def __init__(self, name):
        self.name = name

        # list of visited nodes to avoid recursion and going in circle.
        # can't be a set we store non-hashable objects
        # which is weird why not store memory-location -> object ?
        # anyway...
        self.visited = list()
        self._hash_cache = dict()

        # set of object keys that where deemed worth collecting
        self.collected = set({})
        self.rejected = list()

        # dict of key -> custom spec that should be serialised for comparison
        # later.
        self.spec = dict()

        # debug, make sure 2 objects are not getting the same key
        self._consistency = {}

    def _consistent(self, key, value):
        if key in self._consistency:
            if self._consistency[key] is not value:
                logger.debug("Warning %s is not %s, results may not be consistent" % (
                    self._consistency[key], value))
        else:
            self._consistency[key] = value

    def visit(self, node):
        try:
            if id(node) in [id(x) for x in self.visited]:
                # todo, if visited check the localkey and return it.
                # otherwise methods moved to superclass will/may be lost.
                # or not correctly reported
                return self._hash_cache.get(id(node))
            else:
                self.visited.append(node)
        except TypeError:
            # non equalable things (eg dtype/moduel)
            return
        mod = getattr(node, '__module__', None)
        if mod and not mod.startswith(self.name):
            self.rejected.append(node)
            # print('skipping | ', node.__module__, '|', node)
            return

        if isinstance(node, ModuleType):
            type_ = 'module'
        elif isinstance(node, object) and not isinstance(node, type) and not hasattr(node, '__call__'):
            type_ = 'instance'
        elif issubclass(type(node), type) and type(node) is not type:
            type_ = 'metaclass_instance'
        else:
            type_ = type(node).__name__
        visitor = getattr(self, 'visit_' + type_, self.visit_unknown)
        hashv = visitor(node)
        self._hash_cache[id(node)] = hashv
        return hashv

    def visit_metaclass_instance(self, meta_instance):
        return self.visit_type(meta_instance)
        pass

    def visit_unknown(self, unknown):
        self.rejected.append(unknown)

        logger.debug('Unknown: ========')
        logger.debug('Unknown: No clue what to do with %s', unknown)
        logger.debug('Unknown: isinstance(node, object) %s',
                     isinstance(unknown, object))
        logger.debug('Unknown: isinstance(node, type) %s',
                     isinstance(unknown, type))
        logger.debug('Unknown: type(node) %s', type(unknown))
        if type(unknown) is type:
            logger.debug('Unknown: issubclass(unknown, type) %s',
                         issubclass(unknown, type))
        logger.debug('Unknown: issubclass(type(unknown), type) %s %s',
                     issubclass(type(unknown), type), type(unknown))
        logger.debug('Unknown: type(unknown) is type :  %s',
                     type(unknown) is type)
        logger.debug('Unknown: hasattr(unknown, "__call__"):  %s',
                     hasattr(unknown, "__call__"))
        logger.debug('Unknown: ========')

    def visit_function(self, function):
        klass = function.__class__
        if isinstance(klass, types.FunctionType):
            name = function.__module__
        else:
            name = '%s.%s' % (function.__class__.__module__,
                              function.__class__.__name__)
        fullqual = '{}.{}'.format(name, function.__qualname__)
        # try:
        sig = hexuniformify(str(inspect.signature(function)))
        # except ValueError:
        #    return
        logger.debug('    {f}{s}'.format(f=fullqual, s=sig))
        self.collected.add(fullqual)
        # self.spec[fullqual] = sig
        self.spec[fullqual] = {
            ':signature:': sig_dump(inspect.signature(function))}
        self._consistent(fullqual, function)
        return fullqual

    def visit_instance(self, instance):
        self.rejected.append(instance)
        logger.debug('    vis instance %s', instance)
        pass

    def visit_type(self, type_):
        local_key = type_.__module__ + '.' + type_.__qualname__
        items = {}
        logger.debug('Class %s' % type_.__module__ + '.' + type_.__qualname__)
        for k in sorted(dir(type_)):
            if not k.startswith('_'):
                items[k] = self.visit(getattr(type_, k))
        items = {k: v for k, v in items.items() if v}
        self.spec[local_key] = items
        self.collected.add(local_key)
        return local_key

    def visit_module(self, module):
        logger.debug('Module %s' % module)
        if not module.__name__.startswith(self.name):
            logger.debug('out of scope %s vs %s : %s' % (
                module.__name__, self.name, module.__name__.startswith(self.name)))
            return None
        for k in dir(module):
            if k.startswith('_'):
                logger.debug('       -> %s.%s' % (module.__name__, k))
                continue
            else:
                logger.debug('       +> %s.%s' % (module.__name__, k))
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


def main():
    import argparse

    parser = argparse.ArgumentParser('Argparser for foo')
    parser.add_argument('modules', metavar='modules', type=str,
                        nargs='+', help='root modules and submodules')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--compare', action='store_true')
    parser.add_argument('--debug', action='store_true')

    options = parser.parse_args()

    if options.save and options.compare:
        print('options `--save` and `--compare` are exclusive')
        parser.print_help()

    if options.debug:
        logger.debug('before')
        logger.setLevel('DEBUG')
        logger.debug('after')

    rootname = options.modules[0]
    tree_visitor = Visitor(rootname.split('.')[0])
    for module_name in options.modules:
        try:
            module = importlib.import_module(module_name)
            tree_visitor.visit(module)
        except (ImportError, RuntimeError, AttributeError) as e:
            print('skip...', module_name)
            print(e)

    print("Collected/Visited/rejected", len(tree_visitor.collected),
          len(tree_visitor.visited), len(tree_visitor.rejected), "objects")

    if options.save:
        with open('%s.json' % rootname, 'w') as f:
            f.write(json.dumps(tree_visitor.spec, indent=2))
        #import IPython
        # IPython.embed()
    if options.compare:
        with open('%s.json' % rootname, 'r') as f:
            loaded = json.loads(f.read())

        lkeys = set(loaded.keys())
        skeys = set(tree_visitor.spec.keys())

        common_keys = skeys.intersection(lkeys)
        removed_keys = lkeys.difference(skeys)
        new_keys = skeys.difference(lkeys)
        if new_keys:
            print(
                "The following items are new, former aliases, or where present on superclass")
            pprint(new_keys)
            print()
        if removed_keys:
            print(
                "The following canonical items have been removed, are now aliases or moved to super-class")
            pprint(removed_keys)
            print()

        print("The following signature differ between versions:")
        for key in common_keys:
            if isinstance(loaded[key], str):
                from_dump = hexuniformify(loaded[key])
                current_spec = hexuniformify(tree_visitor.spec[key])
            else:
                from_dump = loaded[key]
                current_spec = tree_visitor.spec[key]

            if from_dump != current_spec:
                if isinstance(current_spec, dict):  # Classes / Module / Fucntion
                    if ':signature:' not in current_spec.keys():
                        removed = [k for k in from_dump if k not in current_spec]
                        if not removed:
                            continue
                        print()
                        print("Class/Module> %current_spec" % (key))
                        new = [k for k in current_spec if k not in from_dump]
                        if new:
                            print('              new values are', new)
                        removed = [k for k in from_dump if k not in current_spec]
                        if removed:
                            print('              removed values are', removed)
                    else:
                        from_dump = from_dump[':signature:']
                        current_spec = current_spec[':signature:']
                        print()
                        print("function> %s" % (key))
                        print("          %s" % (key))
                        params_compare(from_dump, current_spec)


if __name__ == '__main__':
    main()
