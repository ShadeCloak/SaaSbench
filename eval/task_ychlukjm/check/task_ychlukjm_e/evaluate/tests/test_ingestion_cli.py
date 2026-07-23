
from tests._chain_runner import run_node_chain
from utils import NodeResult


def test_cli_doc_propagation_depth_config(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_cli_exit_code_convention(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_cli_ingest_command_runnable(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_cli_kafka_partition_key_urn(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_cli_llm_recipe_yaml_design(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_cli_user_add_with_roles(node: dict) -> NodeResult:
    return run_node_chain(node)

