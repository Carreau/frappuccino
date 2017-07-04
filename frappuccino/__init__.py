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
import sys
import re

from pprint import pprint


from .visitor import BaseVisitor
from .logging import logger

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



class Visitor(BaseVisitor):


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


    def visit_method_descriptor(self, meth):
        pass

    def visit_builtin_function_or_method(self, b):
        pass

    def visit_method(self, b):
        return self.visit_function(b)

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
        self.spec[fullqual] = {
            'type':'function',
            'signature': sig_dump(inspect.signature(function))}
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
        self.spec[local_key] = {
            'type': 'type',
            'items': items
        }
        self.collected.add(local_key)
        return local_key

    def visit_module(self, module):
        logger.debug('Module %s' % module)
        if not module.__name__.startswith(self.name):
            logger.debug('out of scope %s vs %s : %s' % (
                module.__name__, self.name, module.__name__.startswith(self.name)))
            return None
        for k in dir(module):
            if k.startswith('_') and not (k.startswith('__') and k.endswith('__')):
                logger.debug('       skipping private attribute: %s.%s' % (module.__name__, k))
                continue
            else:
                logger.debug('       visiting public attribute; %s.%s' % (module.__name__, k))
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

    parser = argparse.ArgumentParser('frappuccino')
    parser.add_argument('modules', metavar='modules', type=str,
                        nargs='+', help='root modules and submodules')
    parser.add_argument('--save', action='store', help='file to dump API to', metavar='<file>')
    parser.add_argument('--compare', action='store', help='file with dump API to compare to', metavar='<file>')
    parser.add_argument('--debug', action='store_true')

    options = parser.parse_args()

    if options.save and options.compare:
        parser.print_help()
        sys.exit('options `--save` and `--compare` are exclusive')

    if options.debug:
        logger.setLevel('DEBUG')

    rootname = options.modules[0]
    tree_visitor = Visitor(rootname.split('.')[0])
    for module_name in options.modules:
        try:
            module = importlib.import_module(module_name)
            tree_visitor.visit(module)
        except (ImportError, RuntimeError, AttributeError) as e:
            print('skipping ...', module_name)
            print(e)

    print("Collected:", len(tree_visitor.collected),
          "Visited:", len(tree_visitor.visited), 
          "Rejected:", len(tree_visitor.rejected))

    if options.save:
        with open(options.save, 'w') as f:
            f.write(json.dumps(tree_visitor.spec, indent=2))
    if options.compare:
        with open(options.compare, 'r') as f:
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

                if current_spec['type'] == 'type':  # Classes / Module / Fucntion
                    current_spec = current_spec['items']
                    removed = [k for k in from_dump if k not in current_spec]
                    if not removed:
                        continue
                    print()
                    print("Class/Module> %s" % (key))
                    new = [k for k in current_spec if k not in from_dump['items']]
                    if new:
                        print('              new values are', new)
                    removed = [k for k in from_dump if k not in current_spec]
                    if removed:
                        print('              removed values are', removed)
                elif current_spec['type'] == 'function':
                    from_dump = from_dump['signature']
                    current_spec = current_spec['signature']
                    print()
                    print("function> %s" % (key))
                    print("          %s" % (key))
                    params_compare(from_dump, current_spec)
                else:
                    print('unknown node:', current_spec)


if __name__ == '__main__':
    main()
