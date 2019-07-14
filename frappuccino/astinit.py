"""Frappucinno


DEPRECATED/UNUSED

This was a proof of concept trying to visit the AST, though Python is dynamic
enough that this is often too limited. in the end I choose to go with actually
importing things, and walking every reachable object which fully qualified name
does start with give prefixes.

Freeze your API and make sure you do not introduce backward incompatibilities
"""
import ast

test1 = """


class Bird:
    def bar(a,b, *args, kow, **kw ):
        pass

    def foo(c):
        pass


    def missing():
        pass

    def _private():
        pass
"""

test2 = """
class Bird:
    def bar(a,b, *args, kow, **kw ):
        pass

    def foo(c):
        pass

    def _private():
        pass
"""


def keyfy(s):
    return '"%s":' % s


class APIVisitor:
    """
    A node visitor base class that walks the abstract syntax tree and calls a
    visitor function for every node found.  This function may return a value
    which is forwarded by the `visit` method.

    This class is meant to be subclassed, with the subclass adding visitor
    methods.

    Per default the visitor functions for the nodes are ``'visit_'`` +
    class name of the node.  So a `TryFinally` node visit function would
    be `visit_TryFinally`.  This behavior can be changed by overriding
    the `visit` method.  If no visitor function exists for a node
    (return value `None`) the `generic_visit` visitor is used instead.

    Don't use the `NodeVisitor` if you want to apply changes to nodes during
    traversing.  For this a special visitor exists (`NodeTransformer`) that
    allows modifications.
    """

    def visit(self, node):
        """Visit a node."""
        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node):
        """Called if no explicit visitor function exists for a node."""
        res = []
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                for item in value:
                    vv = self.visit(item)
                    res.append(vv)
            elif isinstance(value, dict):
                for k, v in value:
                    res.append(self.visit(v))
                res.append(self.visit(value))
        if not res:
            print("visiting", node)
        return list(filter(None, res))

    def visit_FunctionDef(self, node):
        if node.name.startswith("_"):
            return None
        args = node.args
        return {
            node.name: {
                "type": node.__class__.__name__,
                "args": [a.arg for a in args.args],
                "kwonlyargs": [a.arg for a in args.kwonlyargs],
                "vararg": args.vararg.arg if args.vararg else [],
                "kwarg": args.kwarg.arg if args.kwarg else [],
            }
        }

    def visit_ClassDef(self, node):
        vis = self.generic_visit(node)
        d = {}
        for item in vis:
            d.update(item)
        return {node.name: {"type": node.__class__.__name__, "attributes": d}}


def is_compatible(old_tree, new_tree):
    pass


class DoubleTreeVisitor:
    """
    Like AstVisitor, but compare two tree for compatibility.
    """

    def visit(self, old_list, new_list, name=None):
        """Visit a node."""
        for old_node, new_node in zip(old_list, new_list):
            for k, v in old_node.items():
                if k in new_node:
                    method = "visit_" + v["type"]
                    visitor = getattr(self, method, self.generic_visit)
                    visitor(v, new_node[k], k)

    def generic_visit(self, old_node, new_node):
        """Called if no explicit visitor function exists for a node."""
        res = []
        for field, value in old_node.items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, ast.AST):
                        res.append(self.visit(item))
            elif isinstance(value, ast.AST):
                res.append(self.visit(value))
        return list(filter(None, res))

    def visit_ClassDef(self, old_class, new_class, name):
        missing_attributes = set(old_class["attributes"].keys()).difference(
            set(new_class["attributes"].keys())
        )
        if missing_attributes:
            print(
                "Class `{}` has lost non deprecated and non private "
                "following attributes : {}".format(name, *missing_attributes)
            )

        self.generic_visit(old_class, new_class)


if __name__ == "__main__":
    tree = ast.parse(test1)
    serialized_tree = APIVisitor().visit(tree)

    # pprint(serialized_tree)

    tree2 = ast.parse(test2)
    serialized_tree2 = APIVisitor().visit(tree2)

    dt = DoubleTreeVisitor().visit(serialized_tree, serialized_tree2)
