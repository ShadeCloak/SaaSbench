import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests._chain_runner import execute_chain


def test_CRUD_CAMPAIGN(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_BIZ_CAMPAIGN_STATUS_DRAFT_TO_RUNNING(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_BIZ_CAMPAIGN_STATUS_RUNNING_TO_PAUSED(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_BIZ_CAMPAIGN_STATUS_PAUSED_TO_CANCELLED(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_BIZ_CAMPAIGN_FINISHED_IMMUTABLE(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_BIZ_CAMPAIGN_SCHEDULED_NO_DIRECT_RUNNING(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_BIZ_CAMPAIGN_EDIT_RESTRICTION(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_BIZ_CAMPAIGN_VALIDATION_EMPTY_LISTS(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_BIZ_CAMPAIGN_DEFAULT_FROM_EMAIL(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_BIZ_CAMPAIGN_OPTIN_SUBSCRIBER_FILTER(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_BIZ_CAMPAIGN_RUNNING_TO_CANCELLED(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_LLM_CAMPAIGN_WORKFLOW(node, results, ctx):
    return execute_chain(node, results, ctx)


def test_LLM_CAMPAIGN_WORKFLOW(node, results, ctx):
    return execute_chain(node, results, ctx)

