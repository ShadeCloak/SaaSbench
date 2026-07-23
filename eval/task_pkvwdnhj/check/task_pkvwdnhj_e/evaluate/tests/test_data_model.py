import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests._chain_runner import execute_chain


def test_DEPLOY_DB_TABLES(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_DEPLOY_DB_EXTENSION(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_DB_COLUMNS_SUBSCRIBERS(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_DB_COLUMNS_CAMPAIGNS(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_DB_ENUMS_VERIFY(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_DB_MATVIEWS(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_DB_SETTINGS_DEFAULTS(node, results, ctx):
    return execute_chain(node, results, ctx)

