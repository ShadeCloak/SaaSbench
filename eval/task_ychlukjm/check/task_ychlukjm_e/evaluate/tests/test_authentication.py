
from tests._chain_runner import run_node_chain
from utils import NodeResult


def test_auth_admin_token_management(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_auth_jwt_claims_validation(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_auth_jwt_token_generate(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_auth_nonadmin_token_restriction(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_auth_pat_create_token(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_auth_service_account_token(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_auth_session_token_create(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_auth_system_basic_auth(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_auth_token_expired_reject(node: dict) -> NodeResult:
    return run_node_chain(node)


def test_auth_token_revoke(node: dict) -> NodeResult:
    return run_node_chain(node)

