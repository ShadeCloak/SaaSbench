
from tests._chain_runner import run_node_chain
from utils import NodeResult


def test_api_llm_rest_api_consistency(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_oapi_batch_rollback(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_oapi_dataset_create(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_oapi_dataset_delete(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_oapi_dataset_get(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_oapi_version_match(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_restli_mcp_ingest(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_restli_upsert_auto_create(node: dict) -> NodeResult:
    return run_node_chain(node)

