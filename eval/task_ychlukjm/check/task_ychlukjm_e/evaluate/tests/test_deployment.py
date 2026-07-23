
from tests._chain_runner import run_node_chain
from utils import NodeResult


def test_deploy_elasticsearch_cluster(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_deploy_gradle_build_file(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_deploy_graphql_api(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_deploy_health(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_deploy_kafka_broker(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_deploy_mysql_aspect_table(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_deploy_spring_boot_config(node: dict) -> NodeResult:
    return run_node_chain(node)

