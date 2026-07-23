
from tests._chain_runner import run_node_chain
from utils import NodeResult


def test_biz_assertion_create_run_event(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_biz_data_contract_status_manual_only(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_biz_domain_create_set_entity(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_biz_domain_subdomain_no_depth_limit(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_biz_glossary_term_create_associate(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_biz_incident_state_reversible(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_biz_mcp_async_returns_202(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_biz_mcp_change_type_semantics(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_biz_owner_add_verify_type(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_biz_patch_json_rfc6902(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_biz_structured_prop_type_validation(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_biz_tag_colorhex_no_format_check(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_biz_tag_create_add_remove(node: dict) -> NodeResult:
    return run_node_chain(node)

