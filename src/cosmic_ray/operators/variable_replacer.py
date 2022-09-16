"""Implementation of the variable-replacement operator."""
from .operator import Operator
from .example import Example
from parso.python.tree import Number, ExprStmt, Leaf, PythonNode, IfStmt
from random import randint


class VariableReplacer(Operator):
    """An operator that replaces usages of named variables."""

    def __init__(self, cause_variable, effect_variable=None):
        self.cause_variable = cause_variable
        self.effect_variable = effect_variable

    def mutation_positions(self, node):
        """Replace usages of the cause variable with a constant to remove its causal effect on the effect variable.

           This method identifies all 'suites' that are used to define the value of the effect variable, where a 'suite'
           is a body of code that follows an if statement. The entire suite is later replaced with a copy in which all
           usages of the cause variable are replaced with a randomly sampled numeric constant.

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
                if (self.effect_variable in named_effects) and (self.cause_variable in named_causes):
                    print(f"{self.cause_variable} --> {self.effect_variable}")
                    yield node.start_pos, node.end_pos

    def mutate(self, node, index):
        """Replace 'suite' defining the effect variable with a copy in which the cause variable is absent.

        There are three parts of the 'suite' in which the cause variable can have an effect on the effect variable:
        (1) The predicate of the if statement:          if (X1 + X2 + X3) >= 10:
        (2) The statement of the true branch:               Y1 = X2 + 10
                                                        else:
        (3) The statement of the false branch:              Y1 = X2 + X3 + 4

        In the above example, X1 --> Y1 via the predicate, X2 --> Y1 via the true and false branches, and X3 --> Y1 via
        only the false branch.

        This method finds usages of the specified cause variable in either (1), (2), or (3), and replaces them
        simultaneously with a randomly sampled numeric constant.
        """
        assert isinstance(node, PythonNode) and node.type == "suite", "Error: Node is not a suite."
        print("PRE-MUTATION CODE: ", node.get_code())
        no_causes_node = self._replace_causes_in_suite(node)
        print("POST-MUTATION CODE: ", no_causes_node.get_code())
        return no_causes_node

    def _replace_causes_in_suite(self, node):
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
                        new_arith_expr = self._replace_named_variable_in_expr(arith_expr, self.cause_variable)
                        grandchild_node.children[0] = new_arith_expr
                    # Expressions/statements in true/false branch of if statement
                    elif isinstance(grandchild_node, PythonNode) and grandchild_node.type == "suite":
                        grandchild_node = self._replace_named_variable_in_expr(grandchild_node, self.cause_variable)

        # Replace usages of cause variable in expression nodes
        for expr_node in expr_nodes:
            rhs = expr_node.get_rhs()
            new_rhs = self._replace_named_variable_in_expr(rhs, self.cause_variable)
            expr_node.children[2] = new_rhs

        return node

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

    def _replace_named_variable_in_expr(self, node, variable_name):
        if isinstance(node, Leaf):
            if node.value == variable_name:
                print(node)
                print(node.start_pos, node.end_pos)
                return Number(start_pos=node.start_pos, value=str(randint(-100, 100)), prefix=' ')
            else:
                return node

        updated_child_nodes = []
        for child_node in node.children:
            updated_child_nodes.append(self._replace_named_variable_in_expr(child_node, variable_name))
        node.children = updated_child_nodes
        return node

    @classmethod
    def examples(cls):
        return (
            Example('y = x + z', 'y = 10 + z', operator_args={'cause_variable': 'x'}),
            Example('j = x + z\ny = x + z', 'j = x + z\ny = -2 + z',
                    operator_args={'cause_variable': 'x', 'effect_variable': 'y'}),
            Example('j = x + z\ny = x + z', 'j = 1 + z\ny = x + z',
                    operator_args={'cause_variable': 'x','effect_variable': 'j'}),
            Example('y = 2*x + 10 + j + x**2', 'y=2*10 + 10 + j + -4**2',
                    operator_args={'cause_variable': 'x'}),
        )

