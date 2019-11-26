"""


"""

from types import ModuleType
from .logging import logger as _logger
import inspect
import re

hexd = re.compile("0x[0-9a-f]+")


def hexuniformify(s: str) -> str:
    """
    Uniforming hex addresses to `0xffffff` to avoid difference between rerun.

    Difference  may be due to object id varying in reprs.
    """
    return hexd.sub("0xffffff", s)


def sig_dump(sig):
    """
    Given a signature (from inspect signature), dump ti to json
    """
    return [[k, parameter_dump(v)] for k, v in sig.parameters.items()]


def parameter_dump(p):
    """
    Given a parameter (from inspect signature), dump to to json
    """
    if isinstance(p.default, (int, float, bool)):
        default = p.default
    else:
        default = hexuniformify(str(p.default))
    data = {
        "kind": str(p.kind),
        "name": p.name,
        "default" : default,
    }
    if p.annotation is not inspect._empty:
        data["annotation"]: str(p.annotation)
    return data


class BaseVisitor:
    """
    Visitor base class to recursively walk a give module and all its descendant.

    The generic `visit` method does return a predictable immutable hashable key
    for the given node in order to avoid potential cycles, and to re-compute
    information about a given node.

    Subclass should define multiple methods named `visit_<type(object)>(self,
    object)`, that should return predictable and stable keys for passed object.
    The generic `visit` method will dispatch on the given `visit_*` method when
    it visit a given type, and will fallback on `visit_unknown(self, obj)` if no
    corresponding method is found.


    TODO: figure out and document when to add stuff to rejected, collected, and
    visited, as well as the exact meaning.

    Consider having a `(rejected, reason)` tuple. I can already see a couple of
    reasons:
        1) out of scope (import from another library, which is still exposed)
        2) Private field
        3) Black/whitelisted while in dev.
    """

    def __init__(self, name: str, *, logger=None):
        """

        Parameters
        ==========

        name: str
            Base name of a module to inspect. All found module which fully qualified
            name do not start with this will not be recursed into.
        logger: Logger
            Logger instance to use to print debug messages.

        """

        self.name = name

        # list of visited nodes to avoid recursion and going in circle.
        # can't be a set we store non-hashable objects
        # which is weird why not store memory-location -> object ?
        # anyway...
        self.visited = list()
        self._hash_cache = dict()

        # set of object keys that where deemed worth collecting
        self.collected = set({})

        # list of object we did not visit (for example, we encounter an object
        # not from targeted module, from the stdlib....
        self.rejected = list()

        # dict of key -> custom spec that should be serialised for later
        # comparison later.
        self.spec = dict()

        # debug, make sure 2 objects are not getting the same key
        self._consistency = {}

        if not logger:
            self.logger = _logger
        else:
            self.logger = logger

    def _consistent(self, key, value):
        """
        If the current object we are visiting map to the same key and the same value.

        As we do some normalisation (like for closure that have a `<local>`
        name, we may end up with things conflicting. This is more prevention in
        case on one project at some point we get a collision then we can debug
        that.
        """
        if key in self._consistency:
            if self._consistency[key] is not value:
                self.logger.info(
                    "Warning %s is not %s, results may not be consistent"
                    % (self._consistency[key], value)
                )
        else:
            self._consistency[key] = value

    def visit(self, node):
        """
        Visit current node and return its identification key if visitable.

        If node is not visitable, return `None`.

        """
        try:
            if id(node) in [id(x) for x in self.visited]:
                # todo, if visited check the localkey and return it.
                # otherwise methods moved to superclass will/may be lost.
                # or not correctly reported
                return self._hash_cache.get(id(node))
            else:
                # that seem to be wrong, we likely should put id(node) in that.
                self.visited.append(node)
        except TypeError:
            raise
            # non equalable things (eg dtype/modules)
            return None
        mod = getattr(node, "__module__", None)
        if mod and not mod.startswith(self.name):
            self.rejected.append(node)
            return

        is_callable = hasattr(node, "__call__")
        if isinstance(node, ModuleType):
            type_ = "module"
        elif (
            isinstance(node, object) and not isinstance(node, type) and not is_callable
        ):
            type_ = "instance"
        elif issubclass(type(node), type) and type(node) is not type:
            type_ = "metaclass_instance"
        else:
            type_ = type(node).__name__
        visitor = getattr(self, "visit_" + type_, self.visit_unknown)
        visited_hash = visitor(node)
        self._hash_cache[id(node)] = visited_hash
        return visited_hash


class Visitor(BaseVisitor):
    def visit_metaclass_instance(self, meta_instance):
        return self.visit_type(meta_instance)

    def visit_unknown(self, unknown):
        self.rejected.append(unknown)

        self.logger.debug("Unknown: ========")
        self.logger.debug("Unknown: No clue what to do with %s", unknown)
        self.logger.debug(
            "Unknown: isinstance(node, object) %s", isinstance(unknown, object)
        )
        self.logger.debug(
            "Unknown: isinstance(node, type) %s", isinstance(unknown, type)
        )
        self.logger.debug("Unknown: type(node) %s", type(unknown))
        if type(unknown) is type:
            self.logger.debug(
                "Unknown: issubclass(unknown, type) %s", issubclass(unknown, type)
            )
        self.logger.debug(
            "Unknown: issubclass(type(unknown), type) %s %s",
            issubclass(type(unknown), type),
            type(unknown),
        )
        self.logger.debug("Unknown: type(unknown) is type :  %s", type(unknown) is type)
        self.logger.debug(
            'Unknown: hasattr(unknown, "__call__"):  %s', hasattr(unknown, "__call__")
        )
        self.logger.debug("Unknown: ========")

    def visit_method_descriptor(self, meth):
        self.logger.debug("Unimplemented, visiting_meth_descriptor", meth)

    def visit_builtin_function_or_method(self, bltin):
        try:
            return self.visit_function(bltin)
        except ValueError:
            return 

    def visit_method(self, b):
        return self.visit_function(b)

    def visit_function(self, function):
        name = function.__module__
        if name is None:
            name = "BUILTIN"
        fullqual = "{}.{}".format(name, function.__qualname__)

        ##
        sig = hexuniformify(str(inspect.signature(function)))
        self.logger.debug("    visit_function {f}{s}".format(f=fullqual, s=sig))
        ##

        
        self.collected.add(fullqual)
        if fullqual.startswith("None."):
            import pdb

            pdb.set_trace()
            raise ValueError(function)
        self.spec[fullqual] = {
            "type": "function",
            ## we don't store sign here as they would not be
            ## deep-copyable.
            "signature": sig_dump(inspect.signature(function)),
        }
        self._consistent(fullqual, function)
        return fullqual

    def visit_instance(self, instance):
        self.rejected.append(instance)
        self.logger.debug("    visit_instance %s", instance)
        try:
            return str(instance)
        except Exception:
            print("error in visit instance stringifying")

    def visit_type(self, type_):
        fullqual = type_.__module__ + "." + type_.__qualname__
        items = {}
        self.logger.debug("Class %s" % type_.__module__ + "." + type_.__qualname__)
        for k in sorted(dir(type_)):
            if not k.startswith("_"):
                items[k] = self.visit(getattr(type_, k))
        items = {k: v for k, v in items.items() if v}
        self.spec[fullqual] = {"type": "type", "items": items}
        self.collected.add(fullqual)
        return fullqual

    def visit_module(self, module):
        self.logger.debug("Module %s" % module)
        if not module.__name__.startswith(self.name):
            self.logger.debug(
                "out of scope %s vs %s : %s"
                % (module.__name__, self.name, module.__name__.startswith(self.name))
            )
            return None
        for k in dir(module):
            if k.startswith("_") and not (k.startswith("__") and k.endswith("__")):
                self.logger.debug(
                    "     visit_module: skipping private attribute: %s.%s"
                    % (module.__name__, k)
                )
                continue
            else:
                self.logger.debug(
                    "     visit_module: visiting public attribute; %s.%s"
                    % (module.__name__, k)
                )
                try:
                    mod = getattr(module, k)
                    self.spec[f'{module.__name__}.{k}'] = {'type':'module_item'}
                except ImportError:
                    pass
                    # maybe reject ?

                self.visit(mod)
