import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests._chain_runner import execute_chain


def test_BIZ_BOUNCE_WEBHOOK_RECORD(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_BIZ_BOUNCE_HARD_THRESHOLD_BLOCKLIST(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_BIZ_BOUNCE_SOFT_NO_ACTION(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_LLM_BOUNCE_HANDLING(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_LLM_BOUNCE_HANDLING(node, results, ctx):
    return execute_chain(node, results, ctx)

