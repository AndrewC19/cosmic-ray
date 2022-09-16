"""Implementation of the variable-inserter operator."""
import random
import parso.python.tree
from parso.python.tree import Name, PythonNode, IfStmt, ExprStmt
from .operator import Operator
from .example import Example


class VariableInserter(Operator):
    """An operator that replaces adds usages of named variables to particular statements."""

    def __init__(self, cause_variable, effect_variable):
        self.cause_variable = cause_variable
        self.effect_variable = effect_variable

    def mutation_positions(self, node):
        """Insert usages of the cause variable to statements of the effect variable that are currently unaffected.

           This method identifies all 'suites' that are used to define the value of the effect variable, where a 'suite'
           is a body of code that follows an if statement. The entire suite is later replaced with a copy in which all
           statements of the effect variable are now affected by the cause variable. This is achieved by either adding
           or subtracting the cause variable from the statement.

           :param node: node of parso parse tree that is a potential candidate for mutation.
           :return (start_pos, end_pos): A pair representing the position in the abstract syntax tree to mutate (only if
                                         the mutation operator is applicable at this position).
        """

        if isinstance(node, PythonNode) and node.type == "suite" and isinstance(node.parent, IfStmt):

            # This node is the body of an if-statement.
            # We are only interested in the body of the outer-most if statements that have no else branch.
            if 'else' not in node.parent.children:
                causes, effects = self._get_cause_and_effect_nodes_from_suite_node(node)
                named_causes = [cause.value for cause in causes]
                named_effects = [effect.value for effect in effects]
                if (self.effect_variable in named_effects) and (self.cause_variable not in named_causes):
                    yield node.start_pos, node.end_pos

    def mutate(self, node, index):
        """Join the node with cause variable using a randomly sampled arithmetic operator."""
        assert isinstance(node, PythonNode) and node.type == "suite", "Error: node is not a suite."
        node_with_causes = self._add_causes_to_suite(node)
        return node_with_causes

    def _get_cause_and_effect_nodes_from_suite_node(self, suite_node):
        causes = []  # Variables that appear on RHS of expressions/statements OR in the predicate of an if statement
        effects = []  # Variables appearing on LHS of expressions/statements
        expr_nodes = []  # These are expressions/statements

        for child_node in suite_node.children:
            if isinstance(child_node, ExprStmt):
                expr_nodes.append(child_node)
            elif isinstance(child_node, PythonNode):
                expr_nodes.append(child_node.children[0])
            elif isinstance(child_node, IfStmt):
                for grandchild_node in child_node.children:
                    if isinstance(grandchild_node, PythonNode) and grandchild_node.type == "suite":
                        gc_causes, gc_effects = self._get_cause_and_effect_nodes_from_suite_node(grandchild_node)
                        causes += gc_causes
                        effects += gc_effects
                    elif isinstance(grandchild_node, PythonNode) and grandchild_node.type == "comparison":
                        gc_comparison_causes = list(self._flatten_comparison(grandchild_node))
                        causes += gc_comparison_causes

        for expr_node in expr_nodes:
            causes += list(self._get_causes_from_expr_node(expr_node))
            effects += expr_node.get_defined_names()
        return causes, effects

    def _flatten_expr(self, expr):
        for item in expr:
            # Convert PythonNode to list of its children
            try:
                item_to_flatten = item.children
            except AttributeError:
                item_to_flatten = item
            try:
                yield from self._flatten_expr(item_to_flatten)
            except TypeError:
                yield item_to_flatten

    def _flatten_comparison(self, conditional):
        try:
            # PythonNode (has children)
            to_iterate = conditional.children
        except AttributeError:
            # Not PythonNode (has no children)
            to_iterate = conditional

        for child_node in to_iterate:
            try:
                # If the current node has children, flatten these
                item_to_flatten = child_node.children
            except AttributeError:
                # Otherwise flatted the node itself
                item_to_flatten = child_node

            try:
                yield from self._flatten_comparison(item_to_flatten)
            except TypeError:
                # Non-iterable (leaf node)
                yield item_to_flatten

    def _add_causes_to_suite(self, node):
        expr_nodes = []
        for child_node in node.children:
            # Expression/statement
            if isinstance(child_node, ExprStmt):
                expr_nodes.append(child_node)
            elif isinstance(child_node, PythonNode):
                expr_nodes.append(child_node.children[0])
            # If statement
            elif isinstance(child_node, IfStmt):
                for grandchild_node in child_node.children:
                    # Predicate of if statement
                    if isinstance(grandchild_node, PythonNode) and grandchild_node.type == "comparison":
                        arith_expr = grandchild_node.children[0]
                        new_arith_expr = self._add_cause_to_node(arith_expr)
                        grandchild_node.children[0] = new_arith_expr
                    # Expressions/statements in true/false branch of if statement
                    elif isinstance(grandchild_node, PythonNode) and grandchild_node.type == "suite":
                        grandchild_node = self._add_causes_to_suite(grandchild_node)

        # Replace usages of cause variable in expression nodes
        for expr_node in expr_nodes:
            rhs = expr_node.get_rhs()
            new_rhs = self._add_cause_to_node(rhs)
            expr_node.children[2] = new_rhs

        return node

    def _add_cause_to_node(self, arith_expr_node):
        arith_operator = random.choice(['+', '-'])
        arith_operator_node_start_pos = self._iterate_col(arith_expr_node.end_pos)
        cause_node_start_pos = self._iterate_col(arith_operator_node_start_pos)
        arith_operator_node = parso.python.tree.Operator(arith_operator,
                                                         start_pos=arith_operator_node_start_pos,
                                                         prefix=' ')
        cause_node = Name(self.cause_variable, start_pos=cause_node_start_pos, prefix=' ')
        replacement_node = parso.python.tree.PythonNode("arith_expr",
                                                        [arith_expr_node, arith_operator_node, cause_node])
        return replacement_node

    def _get_causes_from_expr_node(self, expr_node):
        rhs = expr_node.get_rhs().children
        return self._flatten_expr(rhs)

    def _flatten_expr(self, expr):
        for item in expr:
            # Convert PythonNode to list of its children
            try:
                item_to_flatten = item.children
            except AttributeError:
                item_to_flatten = item
            #
            try:
                yield from self._flatten_expr(item_to_flatten)
            except TypeError:
                yield item_to_flatten

    @staticmethod
    def _iterate_col(position_tuple):
        return tuple(sum(x) for x in zip(position_tuple, (0, 1)))

    @classmethod
    def examples(cls):
        return (
            Example('y = x + z', 'y = x + z * j',
                    operator_args={'cause_variable': 'j', 'effect_variable': 'y'}),
            Example('j = x + z\ny = x + z', 'j = x + z + x\ny = x + z',
                    operator_args={'cause_variable': 'x', 'effect_variable': 'j'}),
        )
