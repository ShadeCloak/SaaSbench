import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests._chain_runner import execute_chain


def test_RBAC_SETUP_LIMITED_USER(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_RBAC_SUBSCRIBER_MANAGE_DENY(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_RBAC_SUBSCRIBER_MANAGE_ALLOW(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_RBAC_SETTINGS_DENY(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_RBAC_SETTINGS_ALLOW(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_RBAC_CAMPAIGN_MANAGE_DENY(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_RBAC_CAMPAIGN_MANAGE_ALLOW(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_LLM_RBAC_DESIGN(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_LLM_RBAC_DESIGN(node, results, ctx):
    return execute_chain(node, results, ctx)

