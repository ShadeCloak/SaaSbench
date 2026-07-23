import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests._chain_runner import execute_chain


def test_EDGE_LIST_NAME_EMPTY(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_EDGE_USER_PASSWORD_TOO_SHORT(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_EDGE_CAMPAIGN_SEND_AT_PAST(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_EDGE_ROLE_DUPLICATE_NAME(node, results, ctx):
    return execute_chain(node, results, ctx)

