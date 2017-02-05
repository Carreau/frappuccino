"""
Frappucinno
"""

__version__ = '0.0.1'




import importlib
import inspect
import sys
import types
import json

from pprint import pprint
from types import ModuleType

import logging
logging.basicConfig()
logger = logging.getLogger(__name__)
logger.debug('HO')

def fully_qualified(obj: object) -> str:
    """
    (try to) return the fully qualified name of an object
    """
    if obj is types.FunctionType: # noqa
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
                logger.debug("Warning %s is not %s, results may not be consistent" % (self._consistency[key], value))
        else:
            self._consistency[key] = value



    def visit(self, node):
        try:
            if id(node) in [id(x) for x in self.visited]:
                return
            else:
                self.visited.append(node)
        except TypeError:
            # non equalable things (eg dtype/moduel)
            return
        except ValueError:
            import IPython
            IPython.embed()
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
        return visitor(node)

    def visit_metaclass_instance(self, meta_instance):
        return self.visit_type(meta_instance)
        pass

    def visit_unknown(self, unknown):
        self.rejected.append(unknown)

        logger.debug('Unknown: ========')
        logger.debug('Unknown: No clue what to do with %s', unknown)
        logger.debug('Unknown: isinstance(node, object) %s', isinstance(unknown, object))
        logger.debug('Unknown: isinstance(node, type) %s', isinstance(unknown, type))
        logger.debug('Unknown: type(node) %s', type(unknown))
        if type(unknown) is type:
            logger.debug('Unknown: issubclass(unknown, type) %s', issubclass(unknown, type))
        logger.debug('Unknown: issubclass(type(unknown), type) %s %s', issubclass(type(unknown), type), type(unknown))
        logger.debug('Unknown: type(unknown) is type :  %s', type(unknown) is type)
        logger.debug('Unknown: hasattr(unknown, "__call__"):  %s', hasattr(unknown, "__call__"))
        logger.debug('Unknown: ========')

    def visit_function(self, function):
        klass = function.__class__
        if klass is types.FunctionType:
            name = function.__module__
        else:
            name = '%s.%s' % (function.__class__.__module__, function.__class__.__name__)
        fullqual = '{}.{}'.format(name, function.__qualname__)
        try:
            sig = str(inspect.signature(function))
        except ValueError:
            return
        logger.debug('    {f}{s}'.format(f=fullqual, s=sig))
        self.collected.add(fullqual)
        self.spec[fullqual] = sig
        self._consistent(fullqual, function)
        return fullqual

    def visit_instance(self, instance):
        self.rejected.append(instance)
        logger.debug('    vis instance %s', instance)
        pass


    def visit_type(self, type_):
        local_key = type_.__module__ + '.' + type_.__name__
        items = []
        logger.debug('Class %s' % type_.__module__ + '.' + type_.__name__)
        for k, v in sorted(type_.__dict__.items()):
            if not k.startswith('_'):
                items.append(self.visit(v))
        items = list(filter(None, items))
        self.spec[local_key] = items
        self.collected.add(local_key)
        return local_key


    def visit_module(self, module):
        logger.debug('Module %s' % module)
        if not module.__name__.startswith(self.name):
            logger.debug('out of scope %s vs %s : %s'%(module.__name__, self.name, module.__name__.startswith(self.name)))
            return None
        items = module.__dict__
        for k, v in sorted(items.items()):
            if k.startswith('_'):
                logger.debug('       -> %s.%s' % (module.__name__,k))
                continue
            else:
                logger.debug('       +> %s.%s' % (module.__name__,k))
                res = self.visit(v)





def main():
    import argparse

    parser = argparse.ArgumentParser('Argparser for foo')
    parser.add_argument('modules', metavar='modules', type=str, nargs='+', help='root modules and submodules')
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
    V = Visitor(rootname.split('.')[0])
    for module_name in options.modules:
        try:
            module = importlib.import_module(module_name)
            V.visit(module)
        except (ImportError, RuntimeError):
            print('skip...', module_name)
            pass


    import IPython
    #IPython.embed()


    print("Collected/Visited/rejected", len(V.collected) , len(V.visited), len(V.rejected), "objects")



    if options.save:
        with open('%s.json' % module_name, 'w') as f:
            f.write(json.dumps(V.spec, indent=2))
    if options.compare:
        with open('%s.json' % module_name, 'r') as f:
            loaded = json.loads(f.read())

        lkeys = set(loaded.keys())
        skeys = set(V.spec.keys())

        common_keys = skeys.intersection(lkeys)
        removed_keys = lkeys.difference(skeys)
        new_keys = skeys.difference(lkeys)

        print("The following items are new")
        pprint(new_keys)
        print()

        print("The following items have been removed")
        pprint(removed_keys)
        print()

        print("The following signature differ between versions:")
        for key in common_keys:
            l = loaded[key]
            s = V.spec[key]
            if l != s:
                print()
                print("         %s%s" % (key,l))
                print("current> %s%s" % (key,s))

if __name__ == '__main__':
    main()
