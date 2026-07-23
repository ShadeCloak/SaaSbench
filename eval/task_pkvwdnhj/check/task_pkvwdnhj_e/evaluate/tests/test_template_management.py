import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests._chain_runner import execute_chain


def test_CRUD_TEMPLATE(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_BIZ_TEMPLATE_DEFAULT_SWAP(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_BIZ_TEMPLATE_CONTENT_PLACEHOLDER(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_BIZ_TEMPLATE_DELETE_PROTECTION(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_LLM_TEMPLATE_SYSTEM(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_LLM_TEMPLATE_SYSTEM(node, results, ctx):
    return execute_chain(node, results, ctx)

