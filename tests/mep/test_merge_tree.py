"""Merge-tree synthesis tests.

These exercise the Prim-based drainage tree that the pipe router now uses
to combine multiple fixtures into shared trunk segments. The goal is to
prove both structural correctness (every fixture ends up in the tree and
is reachable from the stack root) and the semantic side-effect the paper
will report on — cumulative discharge units increase monotonically from
leaf to root.
"""

from forge_core.mep_agent.fixture_placer import place_fixtures
from forge_core.mep_agent.merge_tree import annotate_cumulative_du, build_merge_tree
from forge_core.mep_agent.stack_planner import plan_stacks


def test_every_fixture_becomes_a_leaf(multi_storey_office_building):
    fixtures = place_fixtures(multi_storey_office_building)
    fixtures_by_id = {fx.id: fx for fx in fixtures}
    stacks = plan_stacks(multi_storey_office_building, fixtures)
    assert stacks, "test precondition: at least one stack"

    stack = stacks[0]
    tree = build_merge_tree(stack, fixtures_by_id)

    leaves = [n for n in tree.nodes.values() if n.fixture_id is not None]
    assert {n.fixture_id for n in leaves} == set(stack.fixture_ids)


def test_tree_is_rooted_at_the_stack(multi_storey_office_building):
    fixtures = place_fixtures(multi_storey_office_building)
    fixtures_by_id = {fx.id: fx for fx in fixtures}
    stacks = plan_stacks(multi_storey_office_building, fixtures)
    stack = stacks[0]
    tree = build_merge_tree(stack, fixtures_by_id)

    root = tree.nodes[tree.root_id]
    assert root.is_stack_root
    assert root.parent is None
    # Every non-root node must reach the root by climbing parents.
    for node in tree.nodes.values():
        visited = set()
        cursor = node
        while cursor.parent is not None:
            if cursor.id in visited:
                raise AssertionError(f"cycle detected at {cursor.id}")
            visited.add(cursor.id)
            cursor = tree.nodes[cursor.parent]
        assert cursor.id == tree.root_id


def test_cumulative_du_is_monotone_to_root(multi_storey_office_building):
    fixtures = place_fixtures(multi_storey_office_building)
    fixtures_by_id = {fx.id: fx for fx in fixtures}
    stacks = plan_stacks(multi_storey_office_building, fixtures)
    stack = stacks[0]
    tree = build_merge_tree(stack, fixtures_by_id)
    annotate_cumulative_du(tree, fixtures_by_id)

    # The root's cumulative DU must equal the sum of all leaf fixture DUs.
    expected_total = sum(fx.discharge_unit for fx in fixtures if fx.id in stack.fixture_ids)
    assert abs(tree.nodes[tree.root_id].cumulative_du - expected_total) < 1e-6

    # Every edge's parent must carry at least as much DU as its child.
    for child, parent in tree.iter_edges():
        assert parent.cumulative_du + 1e-6 >= child.cumulative_du
