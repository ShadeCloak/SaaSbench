
from tests._chain_runner import run_node_chain
from utils import NodeResult


def test_lifecycle_create_aspect_v0(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_lifecycle_empty_vs_null(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_lifecycle_hard_delete(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_lifecycle_lineage_update(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_lifecycle_owner_add_remove(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_lifecycle_patch_field(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_lifecycle_soft_delete(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_lifecycle_tag_add_remove(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_lifecycle_term_add_remove(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_lifecycle_update_version_history(node: dict) -> NodeResult:
    return run_node_chain(node)

