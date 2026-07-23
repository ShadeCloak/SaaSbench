
from tests._chain_runner import run_node_chain
from utils import NodeResult


def test_api_llm_error_messages_quality(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_api_llm_graphql_schema_quality(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_gql_autocomplete(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_gql_batch_tag_add_atomicity(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_gql_dataset_create(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_gql_dataset_get(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_gql_deprecation_update(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_gql_description_update(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_gql_domain_set(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_gql_error_format(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_gql_null_entity_query(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_gql_owner_add(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_gql_search_across_entities(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_gql_search_basic(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_gql_tag_add(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_gql_term_add(node: dict) -> NodeResult:
    return run_node_chain(node)

