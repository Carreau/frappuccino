"""
Frappucinno
"""




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


        # dict of key -> custom spec that should be serialised for comparison
        # later.
        self.spec = dict()

        # debug, make sure 2 objects are not getting the same key
        self._consistency = {}

    def _consistent(self, key, value):
        if key in self._consistency:
            if self._consistency[key] is not value:
                print("Warning %s is not %s, results may not be consistent" % (self._consistency[key], value))
        else:
            self._consistency[key] = value



    def visit(self, node):

        if node in self.visited:
            return
        else:
            self.visited.append(node)
        mod = getattr(node, '__module__', None)
        if mod and not mod.startswith(self.name):
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

        print('Unknown: ========')
        print('Unknown: No clue what to do with', unknown)
        print('Unknown: isinstance(node, object)', isinstance(unknown, object))
        print('Unknown: isinstance(node, type)', isinstance(unknown, type))
        print('Unknown: type(node)', type(unknown))
        if type(unknown) is type:
            print('Unknown: issubclass(unknown, type)', issubclass(unknown, type))
        print('Unknown: issubclass(type(unknown), type)', issubclass(type(unknown), type), type(unknown))
        print('Unknown: type(unknown) is type : ', type(unknown) is type)
        print('Unknown: hasattr(unknown, "__call__"): ', hasattr(unknown, "__call__"))
        print('Unknown: ========')

    def visit_function(self, function):
        klass = function.__class__
        if klass is types.FunctionType:
            name = function.__module__
        else:
            name = '%s.%s' % (function.__class__.__module__, function.__class__.__name__)
        fullqual = '{}.{}'.format(name, function.__qualname__)
        sig = str(inspect.signature(function))
        logger.debug('    {f}{s}'.format(f=fullqual, s=sig))
        self.collected.add(fullqual)
        self.spec[fullqual] = sig
        self._consistent(fullqual, function)
        return fullqual

    def visit_instance(self, instance):
        log.debug('    vis instance', instance)
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
        return local_key


    def visit_module(self, module):
        logger.debug('Module %s' % module)
        if not module.__name__.startswith(self.name):
            return None
        items = module.__dict__
        for k, v in sorted(items.items()):
            if k.startswith('_'):
                continue
            else:
                res = self.visit(v)





def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--compare', action='store_true')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('modules', nargs='*')

    argparse.ArgumentParser.add_argument

    options = parser.parse_args(sys.argv)
    options.modules.remove('__init__.py')

    if options.save and options.compare:
        print('options `--save` and `--compare` are exclusive')
        parser.print_help()

    if options.debug:
        logger.debug('before')
        logger.setLevel('DEBUG')
        logger.debug('after')


    print("let's go")
    if len(sys.argv) > 1:
        module_name = sys.argv[1]
    else:
        module_name = 'IPython'

    module = __import__(module_name)

    V = Visitor(module_name)
    V.visit(module)
    print("Visited", len(V.visited), "objects")
    print("Collected", len(V.collected), "items")
    if options.save:
        with open('%s.json' % module_name, 'w') as f:
            f.write(json.dumps(V.spec, indent=2))
    if not options.save:
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
