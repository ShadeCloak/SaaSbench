
from tests._chain_runner import run_node_chain
from utils import NodeResult


def test_dm_aspect_primary_key_index(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_dm_aspect_table_columns(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_dm_aspect_versioning_semantics(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_dm_entity_container_graphql(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_dm_entity_corpuser_graphql(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_dm_entity_dataset_graphql(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_dm_entity_policy_graphql(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_dm_system_metadata_structure(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_dm_timeseries_aspect_es(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_dm_urn_format_dataset(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_dm_version_history_increment(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_dm_version_zero_latest(node: dict) -> NodeResult:
    return run_node_chain(node)

