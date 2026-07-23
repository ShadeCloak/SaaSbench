
from tests._chain_runner import run_node_chain
from utils import NodeResult


def test_lineage_add_remove_same_edge(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_lineage_add_upstream_verify(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_lineage_column_level_index(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_lineage_invalid_edge_type_rejected(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_lineage_multi_hop_degree_filter(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_lineage_scroll_pagination(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_lineage_search_across_upstream_structure(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_lineage_update_reorder_verify(node: dict) -> NodeResult:
    return run_node_chain(node)

