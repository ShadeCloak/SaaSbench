
from tests._chain_runner import run_node_chain
from utils import NodeResult


def test_auth_domain_policy_inheritance(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_auth_inactive_policy_deny(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_auth_jwt_login(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_auth_ownership_type_crud(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_auth_ownership_type_mismatch_deny(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_auth_platform_vs_metadata_policy(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_auth_resource_owner_can_edit(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_rbac_admin_can_generate_tokens(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_rbac_admin_can_manage_policies(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_rbac_admin_can_manage_users(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_rbac_editor_can_edit_tags(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_rbac_reader_cannot_edit_tags(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_rbac_reader_cannot_generate_tokens(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_rbac_reader_cannot_manage_policies(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_rbac_reader_cannot_manage_users(node: dict) -> NodeResult:
    return run_node_chain(node)

