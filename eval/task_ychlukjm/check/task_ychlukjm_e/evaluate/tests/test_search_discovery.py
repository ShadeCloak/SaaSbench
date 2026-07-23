
from tests._chain_runner import run_node_chain
from utils import NodeResult


def test_search_autocomplete_case_insensitive(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_search_count_upper_bound(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_search_default_pagination(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_search_default_sort_relevance(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_search_facet_multi_value_or(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_search_filter_or_and_bool(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_search_has_upstreams_index_field(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_search_multi_entity_types(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_search_scroll_entities_pagination(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_search_upstream_leaf_no_upstreams(node: dict) -> NodeResult:
    return run_node_chain(node)

