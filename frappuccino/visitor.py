"""


"""

from types import ModuleType
from .logging import logger as _logger


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
            # non equalable things (eg dtype/modules)
            return None
        mod = getattr(node, "__module__", None)
        if mod and not mod.startswith(self.name):
            self.rejected.append(node)
            return

        if isinstance(node, ModuleType):
            type_ = "module"
        elif (
            isinstance(node, object)
            and not isinstance(node, type)
            and not hasattr(node, "__call__")
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
