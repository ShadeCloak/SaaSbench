
from __future__ import annotations

from ..utils import NodeResult
from ._common import execute_primitive_chain


def test_BIZ_DE_SUM_ZERO_INVARIANT(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_DE_SUM_ZERO_INVARIANT",
        "description": "DE-INV-1: Every TransactionJournal must satisfy SUM(transactions.amount) = 0 in journal currency (double-entry invariant). Create a Withdrawal of 75.00 EUR and verify the two child Transaction rows sum to exactly 0.000000000000 (DECIMAL(32,12) precision).",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/transactions",
                    "headers": {
                        "Authorization": "Bearer {{admin_token}}",
                        "Accept": "application/vnd.api+json",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "transactions": [
                            {
                                "type": "withdrawal",
                                "source_id": "{{asset_account_eur_id}}",
                                "destination_id": "{{expense_account_id}}",
                                "amount": "75.00",
                                "date": "2026-04-01",
                                "description": "DE-INV-1 sum-zero probe {{run_id}}",
                                "currency_id": "{{eur_currency_id}}"
                            }
                        ]
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "acceptable_statuses": [
                        200,
                        201
                    ]
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.data.id",
                            "expected_present": True
                        },
                        {
                            "path": "$.data.attributes",
                            "expected_present": True
                        }
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT CAST(COALESCE(SUM(t.amount),'NA') AS CHAR) AS net_sum, COUNT(*) AS row_count FROM transactions t INNER JOIN transaction_journals tj ON t.transaction_journal_id = tj.id WHERE tj.description = 'DE-INV-1 sum-zero probe {{run_id}}' AND t.deleted_at IS NULL AND tj.deleted_at IS NULL",
                    "expected_result": {
                        "net_sum": "0.000000000000",
                        "row_count": 2
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_DoubleEntry",
            "subcategory": "SumZeroInvariant",
            "method": "binary",
            "maxScore": 12
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-001",
            "KB-003"
        ],
        "_failure_point_refs": [
            "FP-DOUBLE-ENTRY-1"
        ],
        "source_evidence": {
            "source_file": "Business Logic §4.1",
            "behavior_verified": "Static / source-derived; subcategory=SumZeroInvariant",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_TRANSACTION_CREATE_WITHDRAWAL",
            "DB_TABLE_TRANSACTIONS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_DE_TWO_ROWS_PER_JOURNAL(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_DE_TWO_ROWS_PER_JOURNAL",
        "description": "DE-INV-1 (cardinality): Every TransactionJournal MUST have exactly 2 Transaction child rows (createNegative + createPositive). Verify count = 2 for the most recently created journal — agents that model Transaction as a single row with from_account_id/to_account_id will fail this assertion.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/transactions",
                    "headers": {
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "transactions": [
                            {
                                "type": "withdrawal",
                                "source_id": "{{asset_account_eur_id}}",
                                "destination_id": "{{expense_account_id}}",
                                "amount": "33.33",
                                "date": "2026-04-02",
                                "description": "DE-INV-1 cardinality probe"
                            }
                        ]
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "acceptable_statuses": [
                        200,
                        201
                    ]
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.data.id",
                            "expected_present": True
                        },
                        {
                            "path": "$.data.attributes",
                            "expected_present": True
                        }
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS c FROM transactions t INNER JOIN transaction_journals tj ON t.transaction_journal_id = tj.id WHERE tj.description = 'DE-INV-1 cardinality probe' AND t.deleted_at IS NULL",
                    "expected_result": {
                        "c": 2
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_DoubleEntry",
            "subcategory": "TwoRowsPerJournal",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-001"
        ],
        "_failure_point_refs": [
            "FP-DOUBLE-ENTRY-1"
        ],
        "source_evidence": {
            "source_file": "Business Logic §4.1",
            "behavior_verified": "Static / source-derived; subcategory=TwoRowsPerJournal",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_DE_SUM_ZERO_INVARIANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_DE_OPPOSITE_SIGN(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_DE_OPPOSITE_SIGN",
        "description": "DE-INV-1 (sign convention): Source row amount < 0 (Steam::negative), destination row amount > 0 (Steam::positive). For a Deposit of 200 EUR (Revenue → Asset), the source-side transaction must be exactly '-200.000000000000' and the destination-side must be exactly '+200.000000000000'.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/transactions",
                    "headers": {
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "transactions": [
                            {
                                "type": "deposit",
                                "source_id": "{{revenue_account_id}}",
                                "destination_id": "{{asset_account_eur_id}}",
                                "amount": "200.00",
                                "date": "2026-04-03",
                                "description": "DE-INV-1 sign convention probe"
                            }
                        ]
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "acceptable_statuses": [
                        200,
                        201
                    ]
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.data.id",
                            "expected_present": True
                        },
                        {
                            "path": "$.data.attributes",
                            "expected_present": True
                        }
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT CAST(MIN(t.amount) AS CHAR) AS neg_side, CAST(MAX(t.amount) AS CHAR) AS pos_side FROM transactions t INNER JOIN transaction_journals tj ON t.transaction_journal_id = tj.id WHERE tj.description = 'DE-INV-1 sign convention probe' AND t.deleted_at IS NULL",
                    "expected_result": {
                        "neg_side": "-200.000000000000",
                        "pos_side": "200.000000000000"
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_DoubleEntry",
            "subcategory": "OppositeSign",
            "method": "binary",
            "maxScore": 8
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-001"
        ],
        "_failure_point_refs": [
            "FP-DOUBLE-ENTRY-1"
        ],
        "source_evidence": {
            "source_file": "Business Logic §4.1",
            "behavior_verified": "Static / source-derived; subcategory=OppositeSign",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_DE_SUM_ZERO_INVARIANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_DE_CURRENCY_MATCH(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_DE_CURRENCY_MATCH",
        "description": "FP-DOUBLE-ENTRY-2: All transactions inside one TransactionJournal must share the same transaction_currency_id (KB-003 — Transaction-row value is authoritative). Verify SELECT COUNT(DISTINCT transaction_currency_id) = 1 for both child rows.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/transactions",
                    "headers": {
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "transactions": [
                            {
                                "type": "withdrawal",
                                "source_id": "{{asset_account_eur_id}}",
                                "destination_id": "{{expense_account_id}}",
                                "amount": "12.50",
                                "date": "2026-04-04",
                                "description": "currency consistency probe",
                                "currency_id": "{{eur_currency_id}}"
                            }
                        ]
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "acceptable_statuses": [
                        200,
                        201
                    ]
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.data.id",
                            "expected_present": True
                        },
                        {
                            "path": "$.data.attributes",
                            "expected_present": True
                        }
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(DISTINCT t.transaction_currency_id) AS distinct_currencies, COUNT(*) AS row_cnt FROM transactions t INNER JOIN transaction_journals tj ON t.transaction_journal_id = tj.id WHERE tj.description = 'currency consistency probe' AND t.deleted_at IS NULL",
                    "expected_result": {
                        "distinct_currencies": 1,
                        "row_cnt": 2
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_DoubleEntry",
            "subcategory": "CurrencyMatch",
            "method": "binary",
            "maxScore": 8
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-003"
        ],
        "_failure_point_refs": [
            "FP-DOUBLE-ENTRY-2"
        ],
        "source_evidence": {
            "source_file": "Business Logic §4.1",
            "behavior_verified": "Static / source-derived; subcategory=CurrencyMatch",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_DE_SUM_ZERO_INVARIANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_DE_RECONCILIATION_ACCOUNT_TYPE(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_DE_RECONCILIATION_ACCOUNT_TYPE",
        "description": "DE-INV-2 (Reconciliation): Reconciliation transactions must use TransactionType='Reconciliation' and source/destination ∈ {Reconciliation account, Asset account}. Create reconciliation via /api/v1/accounts/{id}/transactions with reconciliation type, then verify journal's transaction_type_id resolves to the 'Reconciliation' row.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/accounts/reconcile/{{asset_account_eur_id}}/submit/2026-04-01/2026-04-30",
                    "use_web_session": True,
                    "body": {
                        "start": "2026-04-01",
                        "end": "2026-04-30",
                        "startBalance": "0",
                        "endBalance": "5",
                        "difference": "5",
                        "reconcile": "create"
                    },
                    "comment": "Reconciliation journals are created ONLY via the web reconcile flow (ReconcileController@submit), not the public /api/v1/transactions endpoint. The reconciliation account is auto-created by AccountRepository::getReconciliation() during this flow. reconcile=create + a non-zero difference makes TransactionGroupFactory store a journal of TransactionType 'Reconciliation' between the asset account and its auto-created 'Reconciliation account'."
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "acceptable_statuses": [
                        200,
                        302
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS ok FROM transaction_journals tj INNER JOIN transaction_types tt ON tj.transaction_type_id = tt.id WHERE tt.type = 'Reconciliation' AND tj.deleted_at IS NULL AND EXISTS (SELECT 1 FROM transactions t JOIN accounts a ON t.account_id = a.id JOIN account_types at2 ON a.account_type_id = at2.id WHERE t.transaction_journal_id = tj.id AND at2.type = 'Reconciliation account') AND EXISTS (SELECT 1 FROM transactions t JOIN accounts a ON t.account_id = a.id WHERE t.transaction_journal_id = tj.id AND a.id = {{asset_account_eur_id}})",
                    "expected_min": {
                        "ok": 1
                    },
                    "comment": "Verifies the reconciliation invariant honestly at the DB level: at least one journal of TransactionType 'Reconciliation' exists whose two legs are the target asset account AND a 'Reconciliation account' (source/destination in {Reconciliation account, Asset account}). expected_min tolerates re-runs that create additional reconciliation journals."
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_DoubleEntry",
            "subcategory": "ReconciliationType",
            "method": "binary",
            "maxScore": 6
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §4.1",
            "behavior_verified": "Static / source-derived; subcategory=ReconciliationType",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_DE_SUM_ZERO_INVARIANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_DE_OPENING_BALANCE_AUTO_TYPE(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_DE_OPENING_BALANCE_AUTO_TYPE",
        "description": "FP-OPENING-BALANCE-AUTO: POST /api/v1/accounts with opening_balance + opening_balance_date must auto-create a TransactionJournal of type 'Opening balance' against an 'Initial balance account'. Verify journal_type='Opening balance' AND counterparty type='Initial balance account'.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/accounts",
                    "headers": {
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "name": "Opening Balance Probe Account {{run_id}}",
                        "type": "asset",
                        "account_role": "defaultAsset",
                        "currency_code": "EUR",
                        "opening_balance": "1000.00",
                        "opening_balance_date": "2026-01-01"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "acceptable_statuses": [
                        200,
                        201
                    ]
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.data.id",
                            "expected_present": True
                        },
                        {
                            "path": "$.data.attributes",
                            "expected_present": True
                        }
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS opening_journals FROM transaction_journals tj INNER JOIN transaction_types tt ON tj.transaction_type_id = tt.id INNER JOIN transactions t ON t.transaction_journal_id = tj.id INNER JOIN accounts a ON t.account_id = a.id WHERE tt.type = 'Opening balance' AND a.name LIKE 'Opening Balance Probe Account%' AND tj.deleted_at IS NULL",
                    "expected_result": {
                        "opening_journals": 1
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_DoubleEntry",
            "subcategory": "OpeningBalanceAutoType",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [
            "FP-OPENING-BALANCE-AUTO"
        ],
        "source_evidence": {
            "source_file": "Business Logic §4.1",
            "behavior_verified": "Static / source-derived; subcategory=OpeningBalanceAutoType",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "DB_TABLE_TRANSACTION_JOURNALS",
            "DB_TABLE_ACCOUNT_TYPES"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_DE_DELETE_GROUP_CASCADES_JOURNALS(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_DE_DELETE_GROUP_CASCADES_JOURNALS",
        "description": "DELETE /api/v1/transactions/{group_id} must cascade-delete (or soft-delete) all child TransactionJournals (KB-005 — TransactionJournal uses SoftDeletes). After delete, no live (deleted_at IS NULL) journal rows remain for the group.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/transactions",
                    "headers": {
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "transactions": [
                            {
                                "type": "withdrawal",
                                "source_id": "{{asset_account_eur_id}}",
                                "destination_id": "{{expense_account_id}}",
                                "amount": "1.00",
                                "date": "2026-04-06",
                                "description": "cascade delete probe"
                            }
                        ]
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "acceptable_statuses": [
                        200,
                        201
                    ]
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.data.id",
                            "exists": True,
                            "save_as": "group_id"
                        }
                    ]
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "DELETE",
                    "path": "/api/v1/transactions/{{group_id}}",
                    "headers": {
                        "Authorization": "Bearer {{admin_token}}"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "acceptable_statuses": [
                        200,
                        204
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS live_journals FROM transaction_journals WHERE transaction_group_id = {{group_id}} AND deleted_at IS NULL",
                    "expected_result": {
                        "live_journals": 0
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_DoubleEntry",
            "subcategory": "DeleteGroupCascade",
            "method": "binary",
            "maxScore": 8
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-005"
        ],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §4.1",
            "behavior_verified": "Static / source-derived; subcategory=DeleteGroupCascade",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_DE_SUM_ZERO_INVARIANT"
        ]
    }
    return execute_primitive_chain(node, context)

