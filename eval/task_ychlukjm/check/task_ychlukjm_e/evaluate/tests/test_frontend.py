
from tests._chain_runner import run_node_chain
from utils import NodeResult


def test_fe_admin_settings_page_exists(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_fe_entity_detail_page_exists(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_fe_lineage_visualization_exists(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_fe_llm_admin_settings_design(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_fe_llm_entity_detail_layout(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_fe_llm_error_empty_states(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_fe_llm_form_interactions(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_fe_llm_global_navigation(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_fe_llm_glossary_domain_tree(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_fe_llm_home_page_quality(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_fe_llm_lineage_visualization(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_fe_llm_search_page_ux(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_fe_navigation_bar_exists(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_fe_search_page_exists(node: dict) -> NodeResult:
    return run_node_chain(node)

