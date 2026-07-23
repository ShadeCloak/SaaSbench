import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests._chain_runner import execute_chain


def test_CRUD_MEDIA(node, results, ctx):
    return execute_chain(node, results, ctx)

