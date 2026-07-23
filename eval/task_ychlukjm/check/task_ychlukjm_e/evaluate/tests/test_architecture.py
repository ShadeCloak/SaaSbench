
from tests._chain_runner import run_node_chain
from utils import NodeResult


def test_arch_api_layering(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_arch_entity_aspect_model(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_arch_event_driven_mcp_mcl(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_arch_llm_auth_architecture(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_arch_llm_data_access_layer(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_arch_llm_error_handling_patterns(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_arch_llm_frontend_code_quality(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_arch_llm_service_layer_design(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_arch_plugin_ingestion_connectors(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_doc_llm_code_documentation(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_doc_llm_logging_quality(node: dict) -> NodeResult:
    return run_node_chain(node)

