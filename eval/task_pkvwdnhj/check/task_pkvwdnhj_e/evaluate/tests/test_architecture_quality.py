import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests._chain_runner import execute_chain


def test_ARCH_CODE_STRUCTURE(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_ARCH_FRONTEND_QUALITY(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_LLM_ERROR_HANDLING(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_LLM_EMAIL_ENGINE(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_LLM_ERROR_HANDLING(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_LLM_EMAIL_ENGINE(node, results, ctx):
    return execute_chain(node, results, ctx)

