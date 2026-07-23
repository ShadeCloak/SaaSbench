import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests._chain_runner import execute_chain


def test_AUTH_FIRST_SETUP(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_AUTH_LOGIN_SESSION(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_AUTH_API_TOKEN_CREATE(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_AUTH_BASIC_AUTH(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_AUTH_LOGOUT(node, results, ctx):
    return execute_chain(node, results, ctx)

