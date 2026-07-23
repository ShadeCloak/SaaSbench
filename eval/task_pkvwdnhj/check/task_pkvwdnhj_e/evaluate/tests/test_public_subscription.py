import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests._chain_runner import execute_chain


def test_API_PUBLIC_LISTS(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_API_PUBLIC_HEALTH(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_LLM_PUBLIC_PAGES(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_LLM_PUBLIC_PAGES(node, results, ctx):
    return execute_chain(node, results, ctx)

