import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests._chain_runner import execute_chain


def test_API_SETTINGS_GET(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_API_SETTINGS_UPDATE(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_API_CONFIG(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_API_ABOUT(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_API_LOGS(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_LLM_SETTINGS_COMPLETENESS(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_LLM_SETTINGS_COMPLETENESS(node, results, ctx):
    return execute_chain(node, results, ctx)

