
from tests._chain_runner import run_node_chain
from utils import NodeResult


def test_edge_concurrent_deadlock_avoidance(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_edge_custom_properties_no_limit(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_edge_glossary_term_source_values(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_edge_graphql_union_unknown_type_null(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_edge_incident_status_reversible(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_edge_patch_last_writer_wins(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_edge_soft_delete_search_invisible(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_edge_urn_length_exceeds_500(node: dict) -> NodeResult:
    return run_node_chain(node)

