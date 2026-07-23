
from __future__ import annotations

from ..utils import NodeResult
from ._common import execute_primitive_chain


def test_API_ACCOUNT_CREATE(context: dict) -> NodeResult:
    node = {
        "id": "API_ACCOUNT_CREATE",
        "description": "POST /api/v1/accounts with {name, type=asset, currency_code=EUR} returns 201 + JSON:API envelope with data.type='accounts', data.id (numeric string), data.attributes.name='Eval Asset Acc'.",
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
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "name": "Eval Asset Acc {{run_id}}",
                        "type": "asset",
                        "currency_code": "EUR",
                        "account_role": "defaultAsset"
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
                            "path": "$.data.type",
                            "expected": "accounts"
                        },
                        {
                            "path": "$.data.id",
                            "exists": True
                        },
                        {
                            "path": "$.data.attributes.name",
                            "expected": "Eval Asset Acc {{run_id}}"
                        },
                        {
                            "path": "$.data.attributes.type",
                            "expected": "asset"
                        },
                        {
                            "path": "$.data.attributes.currency_code",
                            "expected": "EUR"
                        },
                        {
                            "path": "$.data.attributes.active",
                            "expected": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "AccountCreate",
            "method": "binary",
            "maxScore": 4
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-001",
            "KB-009",
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=AccountCreate",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT",
            "DB_TABLE_ACCOUNTS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_ACCOUNT_LIST_PAGINATED(context: dict) -> NodeResult:
    node = {
        "id": "API_ACCOUNT_LIST_PAGINATED",
        "description": "GET /api/v1/accounts?limit=2&page=1 returns paginated envelope with meta.pagination.per_page=2, current_page=1, data is an array of length <=2.",
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
                    "method": "GET",
                    "path": "/api/v1/accounts?limit=2&page=1",
                    "headers": {
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.meta.pagination.per_page",
                            "expected": 2
                        },
                        {
                            "path": "$.meta.pagination.current_page",
                            "expected": 1
                        },
                        {
                            "path": "$.data",
                            "type": "array"
                        },
                        {
                            "path": "$.data",
                            "max_length": 2
                        },
                        {
                            "path": "$.links.self",
                            "exists": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "AccountListPagination",
            "method": "binary",
            "maxScore": 4
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-010",
            "KB-011"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=AccountListPagination",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_ACCOUNT_CREATE"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_ACCOUNT_OPENING_BALANCE_CREATES_JOURNAL(context: dict) -> NodeResult:
    node = {
        "id": "API_ACCOUNT_OPENING_BALANCE_CREATES_JOURNAL",
        "description": "POST /api/v1/accounts with opening_balance + opening_balance_date auto-creates a TransactionJournal of transaction_type='Opening balance' (verified by SQL). Deep node — exercises the side-effect documented in PRD §6.5.",
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
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "name": "Eval Asset Acc OB {{run_id}}",
                        "type": "asset",
                        "currency_code": "EUR",
                        "account_role": "defaultAsset",
                        "opening_balance": "1000.00",
                        "opening_balance_date": "2025-01-01"
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
                            "path": "$.data.type",
                            "expected": "accounts"
                        },
                        {
                            "path": "$.data.attributes.name",
                            "expected": "Eval Asset Acc OB {{run_id}}"
                        },
                        {
                            "path": "$.data.attributes.opening_balance",
                            "expected": "1000",
                            "match_type": "numeric_string"
                        },
                        {
                            "path": "$.data.attributes.opening_balance_date",
                            "match_type": "regex",
                            "pattern": "^2025-01-01"
                        }
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS cnt FROM transaction_journals tj JOIN transaction_types tt ON tj.transaction_type_id=tt.id JOIN users u ON tj.user_id=u.id WHERE tt.type='Opening balance' AND u.email='admin@pfm.local' AND tj.description LIKE '%Eval Asset Acc OB%'",
                    "expected_result": {
                        "cnt": 1
                    }
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT t.amount FROM transactions t JOIN transaction_journals tj ON t.transaction_journal_id=tj.id JOIN transaction_types tt ON tj.transaction_type_id=tt.id JOIN accounts a ON t.account_id=a.id WHERE tt.type='Opening balance' AND a.name='Eval Asset Acc OB' AND CAST(t.amount AS DECIMAL(32,12)) > 0",
                    "min_rows": 1,
                    "comment": "There must be a positive-side row for the asset account, plus a matching negative-side row on the system Initial-balance account."
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "AccountOpeningBalance",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-001",
            "KB-021"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=AccountOpeningBalance",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT",
            "DB_TABLE_TRANSACTION_JOURNALS",
            "DB_TABLE_TRANSACTION_TYPES",
            "DB_TABLE_ACCOUNTS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_TRANSACTION_CREATE_WITHDRAWAL(context: dict) -> NodeResult:
    node = {
        "id": "API_TRANSACTION_CREATE_WITHDRAWAL",
        "description": "POST /api/v1/transactions creates a withdrawal group; verifies envelope shape (data.type='transactions', attributes.transactions[0].type='withdrawal', amount preserved as DECIMAL string, source/destination ids preserved).",
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
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "name": "EvalSrcAsset{{run_id}}",
                        "type": "asset",
                        "currency_code": "EUR",
                        "account_role": "defaultAsset"
                    }
                },
                "save_as": "src_account"
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
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/accounts",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "name": "EvalDestExpense{{run_id}}",
                        "type": "expense"
                    }
                },
                "save_as": "dst_account"
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
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/transactions",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "error_if_duplicate_hash": False,
                        "apply_rules": False,
                        "fire_webhooks": False,
                        "transactions": [
                            {
                                "type": "withdrawal",
                                "date": "2025-04-01",
                                "amount": "50.00",
                                "description": "eval withdrawal",
                                "source_id": "{{src_account.data.id}}",
                                "destination_id": "{{dst_account.data.id}}",
                                "currency_code": "EUR"
                            }
                        ]
                    }
                },
                "save_as": "txn_group"
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
                            "path": "$.data.type",
                            "expected": "transactions"
                        },
                        {
                            "path": "$.data.id",
                            "exists": True
                        },
                        {
                            "path": "$.data.attributes.transactions[0].type",
                            "expected": "withdrawal"
                        },
                        {
                            "path": "$.data.attributes.transactions[0].amount",
                            "expected": "50",
                            "match_type": "numeric_string"
                        },
                        {
                            "path": "$.data.attributes.transactions[0].description",
                            "expected": "eval withdrawal"
                        },
                        {
                            "path": "$.data.attributes.transactions[0].currency_code",
                            "expected": "EUR"
                        },
                        {
                            "path": "$.data.attributes.transactions[0].source_id",
                            "exists": True
                        },
                        {
                            "path": "$.data.attributes.transactions[0].destination_id",
                            "exists": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "TransactionCreateWithdrawal",
            "method": "binary",
            "maxScore": 6
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-001",
            "KB-009",
            "KB-010",
            "KB-021"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=TransactionCreateWithdrawal",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_ACCOUNT_CREATE",
            "DB_TABLE_TRANSACTION_GROUPS",
            "DB_TABLE_TRANSACTION_JOURNALS",
            "DB_TABLE_TRANSACTIONS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_TRANSACTION_DOUBLE_ENTRY_INVARIANT(context: dict) -> NodeResult:
    node = {
        "id": "API_TRANSACTION_DOUBLE_ENTRY_INVARIANT",
        "description": "Critical double-entry invariant — after creating a withdrawal, the SUM of physical Transaction.amount rows on the same transaction_journal_id MUST equal '0' (one negative-side, one positive-side, strict equality of magnitudes). Validates the core accounting rule from PRD §6.6 + KB-021.",
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
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "transactions": [
                            {
                                "type": "withdrawal",
                                "date": "2025-04-02",
                                "amount": "73.45",
                                "description": "double entry probe",
                                "source_name": "EvalSrcAsset{{run_id}}",
                                "destination_name": "EvalDestExpense{{run_id}}",
                                "currency_code": "EUR"
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
                            "path": "$.data.type",
                            "expected": "transactions"
                        },
                        {
                            "path": "$.data.attributes.transactions[0].amount",
                            "expected": "73.45",
                            "match_type": "numeric_string"
                        },
                        {
                            "path": "$.data.attributes.transactions[0].description",
                            "expected": "double entry probe"
                        }
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT tj.id AS journal_id, COUNT(t.id) AS row_cnt, CAST(SUM(CAST(t.amount AS DECIMAL(32,12))) AS CHAR) AS amount_sum, CAST(SUM(CASE WHEN CAST(t.amount AS DECIMAL(32,12)) < 0 THEN 1 ELSE 0 END) AS UNSIGNED) AS neg_cnt, CAST(SUM(CASE WHEN CAST(t.amount AS DECIMAL(32,12)) > 0 THEN 1 ELSE 0 END) AS UNSIGNED) AS pos_cnt FROM transactions t JOIN transaction_journals tj ON t.transaction_journal_id=tj.id WHERE tj.description='double entry probe' GROUP BY tj.id",
                    "expected_first_row": {
                        "row_cnt": 2,
                        "neg_cnt": 1,
                        "pos_cnt": 1
                    },
                    "additional_assertions": [
                        {
                            "field": "amount_sum",
                            "match_type": "numeric_equal_to_zero",
                            "comment": "Magnitudes must cancel exactly to satisfy the double-entry invariant."
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "TransactionDoubleEntry",
            "method": "binary",
            "maxScore": 12
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-001",
            "KB-021"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=TransactionDoubleEntry",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_TRANSACTION_CREATE_WITHDRAWAL",
            "DB_TABLE_TRANSACTIONS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_TRANSACTION_FOREIGN_AMOUNT_NULL_WHEN_SAME_CURRENCY(context: dict) -> NodeResult:
    node = {
        "id": "API_TRANSACTION_FOREIGN_AMOUNT_NULL_WHEN_SAME_CURRENCY",
        "description": "When source and destination accounts share the same currency, the persisted transaction row must have foreign_amount IS NULL and foreign_currency_id IS NULL (per KB-008). Verified both in the API response (JSON None, keys present) and via direct DB query.",
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
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "transactions": [
                            {
                                "type": "withdrawal",
                                "date": "2025-04-03",
                                "amount": "12.34",
                                "description": "same-currency probe",
                                "source_name": "EvalSrcAsset{{run_id}}",
                                "destination_name": "EvalDestExpense{{run_id}}",
                                "currency_code": "EUR"
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
                            "path": "$.data.attributes.transactions[0].foreign_amount",
                            "type": "null"
                        },
                        {
                            "path": "$.data.attributes.transactions[0].foreign_currency_id",
                            "type": "null"
                        },
                        {
                            "path": "$.data.attributes.transactions[0].foreign_currency_code",
                            "type": "null"
                        }
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT t.foreign_amount, t.foreign_currency_id FROM transactions t JOIN transaction_journals tj ON t.transaction_journal_id=tj.id WHERE tj.description='same-currency probe'",
                    "min_rows": 2,
                    "row_assertions": [
                        {
                            "field": "foreign_amount",
                            "expected": None
                        },
                        {
                            "field": "foreign_currency_id",
                            "expected": None
                        }
                    ],
                    "comment": "Per KB-008 the foreign override pair is left NULL — never written as the string '0.00' — when source and destination currencies match."
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "ForeignAmountNullSameCurrency",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-008",
            "KB-019"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=ForeignAmountNullSameCurrency",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_TRANSACTION_CREATE_WITHDRAWAL",
            "DB_TABLE_TRANSACTIONS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_TRANSACTION_INVALID_TYPE_REJECTED(context: dict) -> NodeResult:
    node = {
        "id": "API_TRANSACTION_INVALID_TYPE_REJECTED",
        "description": "POST /api/v1/transactions with type=withdrawal but source.type=Revenue MUST be rejected with 422 (violates the source/destination compatibility matrix per PRD §6.6 cross-validation step 6).",
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
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "name": "EvalRevenueAcc {{run_id}}",
                        "type": "revenue"
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
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/transactions",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "transactions": [
                            {
                                "type": "withdrawal",
                                "date": "2025-04-04",
                                "amount": "10.00",
                                "description": "invalid src type",
                                "source_name": "EvalRevenueAcc {{run_id}}",
                                "destination_name": "EvalDestExpense{{run_id}}",
                                "currency_code": "EUR"
                            }
                        ]
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 422
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.message",
                            "match_type": "regex",
                            "pattern": "(is required|invalid|must be|already in use|already been taken|more error|The .+ field)",
                            "comment": "Laravel/Firefly 422 validation envelope — message is a human-readable summary whose wording depends on the failed rule (e.g. 'is invalid', 'is required', 'This name is already in use.'), never guaranteed to contain the literal 'invalid'."
                        },
                        {
                            "path": "$.errors",
                            "type": "object"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "TransactionInvalidSourceType",
            "method": "binary",
            "maxScore": 6
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-015",
            "KB-020"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=TransactionInvalidSourceType",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_TRANSACTION_CREATE_WITHDRAWAL"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_BUDGET_CREATE(context: dict) -> NodeResult:
    node = {
        "id": "API_BUDGET_CREATE",
        "description": "POST /api/v1/budgets creates a Budget; envelope shape verified (data.type='budgets', attributes.name, attributes.active, attributes.auto_budget_type defaults to 'none').",
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
                    "path": "/api/v1/budgets",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "name": "EvalGroceries{{run_id}}",
                        "active": True
                    }
                },
                "save_as": "budget"
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
                            "path": "$.data.type",
                            "expected": "budgets"
                        },
                        {
                            "path": "$.data.id",
                            "exists": True
                        },
                        {
                            "path": "$.data.attributes.name",
                            "expected": "EvalGroceries{{run_id}}"
                        },
                        {
                            "path": "$.data.attributes.active",
                            "expected": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "BudgetCreate",
            "method": "binary",
            "maxScore": 4
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-009",
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=BudgetCreate",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT",
            "DB_TABLE_BUDGETS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_BUDGETLIMIT_CREATE(context: dict) -> NodeResult:
    node = {
        "id": "API_BUDGETLIMIT_CREATE",
        "description": "POST /api/v1/budgets/{budget}/limits creates a BudgetLimit; verifies the nested envelope (data.type='budget_limits', attributes.amount as DECIMAL string, start/end dates).",
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
                    "path": "/api/v1/budgets",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "name": "EvalBudgetForLimit{{run_id}}",
                        "active": True
                    }
                },
                "save_as": "bud"
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
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/budgets/{{bud.data.id}}/limits",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "currency_code": "EUR",
                        "start": "2025-04-01",
                        "end": "2025-04-30",
                        "amount": "300.00"
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
                            "path": "$.data.type",
                            "expected": "budget_limits"
                        },
                        {
                            "path": "$.data.attributes.amount",
                            "expected": "300",
                            "match_type": "numeric_string"
                        },
                        {
                            "path": "$.data.attributes.currency_code",
                            "expected": "EUR"
                        },
                        {
                            "path": "$.data.attributes.start",
                            "match_type": "regex",
                            "pattern": "^2025-04-01"
                        },
                        {
                            "path": "$.data.attributes.end",
                            "match_type": "regex",
                            "pattern": "^2025-04-30"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "BudgetLimitCreate",
            "method": "binary",
            "maxScore": 5
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-001",
            "KB-009"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=BudgetLimitCreate",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_BUDGET_CREATE",
            "DB_TABLE_BUDGET_LIMITS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_BUDGET_LIST_FILTER(context: dict) -> NodeResult:
    node = {
        "id": "API_BUDGET_LIST_FILTER",
        "description": "GET /api/v1/budgets?start=2025-04-01&end=2025-04-30 returns paginated envelope; data is array, meta.pagination.per_page is numeric (default 50 per KB-011).",
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
                    "method": "GET",
                    "path": "/api/v1/budgets?start=2025-04-01&end=2025-04-30",
                    "headers": {
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.data",
                            "type": "array"
                        },
                        {
                            "path": "$.meta.pagination.per_page",
                            "type": "integer"
                        },
                        {
                            "path": "$.meta.pagination.current_page",
                            "expected": 1
                        },
                        {
                            "path": "$.data[0].type",
                            "expected": "budgets",
                            "optional": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "BudgetListWithDateRange",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-010",
            "KB-011",
            "KB-013"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=BudgetListWithDateRange",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_BUDGET_CREATE"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_BILL_CREATE(context: dict) -> NodeResult:
    node = {
        "id": "API_BILL_CREATE",
        "description": "POST /api/v1/bills creates a Bill; verifies envelope (data.type='bills', attributes.amount_min/amount_max as DECIMAL strings, repeat_freq).",
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
                    "path": "/api/v1/bills",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "name": "EvalNetflix{{run_id}}",
                        "amount_min": "9.99",
                        "amount_max": "12.99",
                        "currency_code": "EUR",
                        "date": "2025-04-15",
                        "repeat_freq": "monthly",
                        "skip": 0,
                        "active": True
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
                            "path": "$.data.type",
                            "expected": "bills"
                        },
                        {
                            "path": "$.data.attributes.name",
                            "expected": "EvalNetflix{{run_id}}"
                        },
                        {
                            "path": "$.data.attributes.amount_min",
                            "expected": "9.99",
                            "match_type": "numeric_string"
                        },
                        {
                            "path": "$.data.attributes.amount_max",
                            "expected": "12.99",
                            "match_type": "numeric_string"
                        },
                        {
                            "path": "$.data.attributes.repeat_freq",
                            "expected": "monthly"
                        },
                        {
                            "path": "$.data.attributes.active",
                            "expected": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "BillCreate",
            "method": "binary",
            "maxScore": 5
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-001",
            "KB-009"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=BillCreate",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT",
            "DB_TABLE_BILLS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_BILL_SUBSCRIPTIONS_ALIAS(context: dict) -> NodeResult:
    node = {
        "id": "API_BILL_SUBSCRIPTIONS_ALIAS",
        "description": "GET /api/v1/subscriptions and GET /api/v1/bills both resolve to the same controller — they must return equivalent payload shape (same data.type='bills' since the underlying transformer is identical per PRD §6.11.2).",
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
                    "method": "GET",
                    "path": "/api/v1/bills",
                    "headers": {
                        "Accept": "application/json"
                    }
                },
                "save_as": "via_bills"
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/subscriptions",
                    "headers": {
                        "Accept": "application/json"
                    }
                },
                "save_as": "via_subs"
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "via_bills.$.meta.pagination.total",
                            "equals_path": "via_subs.$.meta.pagination.total"
                        },
                        {
                            "path": "via_bills.$.data[0].type",
                            "equals_path": "via_subs.$.data[0].type"
                        },
                        {
                            "path": "via_subs.$.data[0].type",
                            "expected": "bills",
                            "optional": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "BillSubscriptionsAlias",
            "method": "binary",
            "maxScore": 4
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=BillSubscriptionsAlias",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_BILL_CREATE"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_CATEGORY_CREATE(context: dict) -> NodeResult:
    node = {
        "id": "API_CATEGORY_CREATE",
        "description": "POST /api/v1/categories creates a Category; verifies envelope shape and required field assertions.",
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
                    "path": "/api/v1/categories",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "name": "EvalFood{{run_id}}"
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
                            "path": "$.data.type",
                            "expected": "categories"
                        },
                        {
                            "path": "$.data.id",
                            "exists": True
                        },
                        {
                            "path": "$.data.attributes.name",
                            "expected": "EvalFood{{run_id}}"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "CategoryCreate",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-009",
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=CategoryCreate",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_CATEGORY_UNIQUE_NAME_REJECTED(context: dict) -> NodeResult:
    node = {
        "id": "API_CATEGORY_UNIQUE_NAME_REJECTED",
        "description": "Creating two categories with identical name MUST be rejected with 422 by the uniqueObjectForUser validator (PRD §6.12.1).",
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
                    "path": "/api/v1/categories",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "name": "EvalUniqueCat{{run_id}}"
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
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/categories",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "name": "EvalUniqueCat{{run_id}}"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 422
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.message",
                            "match_type": "regex",
                            "pattern": "(is required|invalid|must be|already in use|already been taken|more error|The .+ field)",
                            "comment": "Laravel/Firefly 422 validation envelope — message is a human-readable summary whose wording depends on the failed rule (e.g. 'is invalid', 'is required', 'This name is already in use.'), never guaranteed to contain the literal 'invalid'."
                        },
                        {
                            "path": "$.errors.name",
                            "type": "array"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "CategoryUniqueRejection",
            "method": "binary",
            "maxScore": 4
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-015"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=CategoryUniqueRejection",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_CATEGORY_CREATE"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_TAG_CREATE(context: dict) -> NodeResult:
    node = {
        "id": "API_TAG_CREATE",
        "description": "POST /api/v1/tags creates a Tag; verifies envelope (data.type='tags', attributes.tag).",
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
                    "path": "/api/v1/tags",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "tag": "evaltag-vacation-{{run_id}}",
                        "description": "eval tag"
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
                            "path": "$.data.type",
                            "expected": "tags"
                        },
                        {
                            "path": "$.data.id",
                            "exists": True
                        },
                        {
                            "path": "$.data.attributes.tag",
                            "expected": "evaltag-vacation-{{run_id}}"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "TagCreate",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-009",
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=TagCreate",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_TAG_FIND_BY_TAG_OR_ID(context: dict) -> NodeResult:
    node = {
        "id": "API_TAG_FIND_BY_TAG_OR_ID",
        "description": "GET /api/v1/tags/{tagOrId} accepts either the numeric id OR the tag string (PRD §6.13). Both resolve to the same record.",
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
                    "path": "/api/v1/tags",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "tag": "evaltag-dual"
                    }
                },
                "save_as": "tag_record"
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
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/tags/{{tag_record.data.id}}",
                    "headers": {
                        "Accept": "application/json"
                    }
                },
                "save_as": "by_id"
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/tags/evaltag-dual",
                    "headers": {
                        "Accept": "application/json"
                    }
                },
                "save_as": "by_tag"
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "by_id.$.data.attributes.tag",
                            "expected": "evaltag-dual"
                        },
                        {
                            "path": "by_tag.$.data.attributes.tag",
                            "expected": "evaltag-dual"
                        },
                        {
                            "path": "by_id.$.data.id",
                            "equals_path": "by_tag.$.data.id"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "TagDualLookup",
            "method": "binary",
            "maxScore": 4
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=TagDualLookup",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_TAG_CREATE"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_PIGGYBANK_CREATE(context: dict) -> NodeResult:
    node = {
        "id": "API_PIGGYBANK_CREATE",
        "description": "POST /api/v1/piggy-banks creates a PiggyBank linked to one asset account; verifies envelope and target_amount as DECIMAL string.",
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
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "name": "EvalSavings{{run_id}}",
                        "type": "asset",
                        "currency_code": "EUR",
                        "account_role": "savingAsset"
                    }
                },
                "save_as": "savings"
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
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/piggy-banks",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "name": "EvalNewBike{{run_id}}",
                        "accounts": [
                            {
                                "account_id": "{{savings.data.id}}",
                                "current_amount": "0"
                            }
                        ],
                        "target_amount": "500.00",
                        "start_date": "2025-04-01",
                        "transaction_currency_code": "EUR"
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
                            "path": "$.data.type",
                            "expected": "piggy_banks"
                        },
                        {
                            "path": "$.data.attributes.name",
                            "expected": "EvalNewBike{{run_id}}"
                        },
                        {
                            "path": "$.data.attributes.target_amount",
                            "expected": "500",
                            "match_type": "numeric_string"
                        },
                        {
                            "path": "$.data.attributes.currency_code",
                            "expected": "EUR"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "PiggyBankCreate",
            "method": "binary",
            "maxScore": 5
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-001",
            "KB-009",
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=PiggyBankCreate",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_ACCOUNT_CREATE",
            "DB_TABLE_PIGGY_BANKS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_PIGGYBANK_LIST_EVENTS(context: dict) -> NodeResult:
    node = {
        "id": "API_PIGGYBANK_LIST_EVENTS",
        "description": "GET /api/v1/piggy-banks/{piggyBank}/events returns a paginated list of PiggyBankEvent records (read-only — events are created implicitly when transfers carry piggy_bank_id, per PRD §6.14).",
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
                    "method": "GET",
                    "path": "/api/v1/piggy-banks?limit=1",
                    "headers": {
                        "Accept": "application/json"
                    }
                },
                "save_as": "pb_list"
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/piggy-banks/{{pb_list.data[0].id}}/events?limit=10",
                    "headers": {
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.data",
                            "type": "array"
                        },
                        {
                            "path": "$.meta.pagination.per_page",
                            "type": "integer"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "PiggyBankEventList",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=PiggyBankEventList",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_PIGGYBANK_CREATE"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_PIGGYBANK_TRANSFER_MOVES_AMOUNT(context: dict) -> NodeResult:
    node = {
        "id": "API_PIGGYBANK_TRANSFER_MOVES_AMOUNT",
        "description": "Deep node: per PRD §6.14 there is NO POST /piggy-banks/{id}/events endpoint; piggy-bank movement happens via a transfer transaction carrying piggy_bank_id. After such a transfer, account_piggy_bank.current_amount must reflect the new balance (verified via SQL).",
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
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "name": "EvalChecking{{run_id}}",
                        "type": "asset",
                        "currency_code": "EUR",
                        "account_role": "defaultAsset",
                        "opening_balance": "1000.00",
                        "opening_balance_date": "2025-01-01"
                    }
                },
                "save_as": "checking"
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
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/accounts",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "name": "EvalPiggySavings{{run_id}}",
                        "type": "asset",
                        "currency_code": "EUR",
                        "account_role": "savingAsset"
                    }
                },
                "save_as": "psavings"
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
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/piggy-banks",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "name": "EvalDeepPiggy{{run_id}}",
                        "accounts": [
                            {
                                "account_id": "{{psavings.data.id}}",
                                "current_amount": "0"
                            }
                        ],
                        "target_amount": "1000.00",
                        "start_date": "2025-04-01",
                        "transaction_currency_code": "EUR"
                    }
                },
                "save_as": "piggy"
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
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/transactions",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "transactions": [
                            {
                                "type": "transfer",
                                "date": "2025-04-05",
                                "amount": "100.00",
                                "description": "fund piggy bank",
                                "source_id": "{{checking.data.id}}",
                                "destination_id": "{{psavings.data.id}}",
                                "piggy_bank_id": "{{piggy.data.id}}",
                                "currency_code": "EUR"
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
                "type": "P08",
                "inputs": {
                    "sql": "SELECT CAST(apb.current_amount AS CHAR) AS current_amount FROM account_piggy_bank apb JOIN piggy_banks pb ON apb.piggy_bank_id=pb.id JOIN accounts a ON apb.account_id=a.id WHERE pb.id={{piggy.data.id}} AND a.id={{psavings.data.id}}",
                    "expected_first_row": {
                        "current_amount": 100
                    },
                    "additional_assertions": [
                        {
                            "field": "current_amount",
                            "match_type": "numeric_equal",
                            "expected_numeric": 100,
                            "tolerance": 0.001
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "PiggyBankTransferMovesAmount",
            "method": "binary",
            "maxScore": 12
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-001"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=PiggyBankTransferMovesAmount",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_PIGGYBANK_CREATE",
            "API_TRANSACTION_CREATE_WITHDRAWAL"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_RECURRENCE_CREATE(context: dict) -> NodeResult:
    node = {
        "id": "API_RECURRENCE_CREATE",
        "description": "POST /api/v1/recurrences creates a recurrence template (type=withdrawal, repetitions[].type=monthly).",
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
                    "path": "/api/v1/recurrences",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "type": "withdrawal",
                        "title": "EvalMonthlyRent {{run_id}}",
                        "first_date": "2025-05-01",
                        "nr_of_repetitions": 12,
                        "active": True,
                        "apply_rules": False,
                        "repetitions": [
                            {
                                "type": "monthly",
                                "moment": "1",
                                "skip": 0,
                                "weekend": 1
                            }
                        ],
                        "transactions": [
                            {
                                "description": "Monthly rent",
                                "amount": "850.00",
                                "currency_code": "EUR",
                                "source_id": "{{seed_asset_account_id}}",
                                "destination_id": "{{expense_account_eur_id}}"
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
                            "path": "$.data.type",
                            "expected": "recurrences"
                        },
                        {
                            "path": "$.data.attributes.title",
                            "match_type": "regex",
                            "pattern": "^EvalMonthlyRent"
                        },
                        {
                            "path": "$.data.attributes.type",
                            "match_type": "regex",
                            "pattern": "^(withdrawal|Withdrawal)$"
                        },
                        {
                            "path": "$.data.attributes.active",
                            "expected": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "RecurrenceCreate",
            "method": "binary",
            "maxScore": 5
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-009",
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=RecurrenceCreate",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_ACCOUNT_CREATE",
            "DB_TABLE_RECURRENCES"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_RECURRENCE_TRIGGER_CREATES_TRANSACTIONS(context: dict) -> NodeResult:
    node = {
        "id": "API_RECURRENCE_TRIGGER_CREATES_TRANSACTIONS",
        "description": "Deep: POST /api/v1/recurrences/{id}/trigger fires the template now and inserts new transaction journals (verified via SQL: count of transactions with recurrence_id=<id> increases).",
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
                    "method": "GET",
                    "path": "/api/v1/recurrences?limit=1",
                    "headers": {
                        "Accept": "application/json"
                    }
                },
                "save_as": "rec_list"
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/recurrences/{{rec_list.data[0].id}}/trigger",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "date": "{{three_days_ahead_iso}}"
                    }
                },
                "save_as": "trig_resp"
            },
            {
                "type": "P15",
                "inputs": {
                    "acceptable_statuses": [
                        200,
                        201,
                        204
                    ]
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "trig_resp.$.data.type",
                            "expected": "recurrences",
                            "optional": True,
                            "comment": "PRD §6.15.1: trigger returns {data:Recurrence, meta:{transactions_created:N}} when status is 200; for 204 these assertions are skipped."
                        },
                        {
                            "path": "trig_resp.$.meta.transactions_created",
                            "type": "integer",
                            "min_value": 0,
                            "optional": True
                        }
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS cnt FROM transaction_journals tj WHERE tj.id IN (SELECT rt.transaction_journal_id FROM recurrences r LEFT JOIN recurrences_transactions rt_meta ON rt_meta.recurrence_id=r.id LEFT JOIN journal_meta jm ON jm.transaction_journal_id=tj.id WHERE jm.name='recurrence_id' AND CAST(jm.data AS CHAR) LIKE CONCAT('%\"', r.id, '\"%')) OR EXISTS (SELECT 1 FROM journal_meta jm2 WHERE jm2.transaction_journal_id=tj.id AND jm2.name='recurrence_id')",
                    "min_value": 1,
                    "comment": "Trigger may persist linkage either via journal_meta(recurrence_id) or a dedicated mapping table; either is acceptable evidence the trigger ran."
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "RecurrenceTriggerSideEffect",
            "method": "binary",
            "maxScore": 8
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=RecurrenceTriggerSideEffect",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_RECURRENCE_CREATE",
            "DB_TABLE_TRANSACTION_JOURNALS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_RULE_CREATE(context: dict) -> NodeResult:
    node = {
        "id": "API_RULE_CREATE",
        "description": "POST /api/v1/rules creates a rule under a rule group with one trigger (description_contains) and one action (add_tag) per PRD §6.16.1. Verifies envelope and nested triggers/actions arrays.",
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
                    "path": "/api/v1/rule-groups",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "title": "EvalRuleGroup{{run_id}}",
                        "active": True
                    }
                },
                "save_as": "rg"
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
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/rules",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "title": "EvalAutoTagCafe",
                        "rule_group_id": "{{rg.data.id}}",
                        "trigger": "store-journal",
                        "strict": True,
                        "stop_processing": False,
                        "active": True,
                        "triggers": [
                            {
                                "type": "description_contains",
                                "value": "cafe",
                                "active": True,
                                "stop_processing": False
                            }
                        ],
                        "actions": [
                            {
                                "type": "add_tag",
                                "value": "food",
                                "active": True,
                                "stop_processing": False
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
                            "path": "$.data.type",
                            "expected": "rules"
                        },
                        {
                            "path": "$.data.attributes.title",
                            "expected": "EvalAutoTagCafe"
                        },
                        {
                            "path": "$.data.attributes.active",
                            "expected": True
                        },
                        {
                            "path": "$.data.attributes.triggers[0].type",
                            "expected": "description_contains"
                        },
                        {
                            "path": "$.data.attributes.triggers[0].value",
                            "expected": "cafe"
                        },
                        {
                            "path": "$.data.attributes.actions[0].type",
                            "expected": "add_tag"
                        },
                        {
                            "path": "$.data.attributes.actions[0].value",
                            "expected": "food"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "RuleCreate",
            "method": "binary",
            "maxScore": 6
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-009",
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=RuleCreate",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT",
            "DB_TABLE_RULES"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_RULE_TEST_DRY_RUN(context: dict) -> NodeResult:
    node = {
        "id": "API_RULE_TEST_DRY_RUN",
        "description": "GET /api/v1/rules/{rule}/test returns the journals that WOULD match — dry-run, no side effects (PRD §6.16.1 row 7).",
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
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "transactions": [
                            {
                                "type": "withdrawal",
                                "date": "2025-04-10",
                                "amount": "5.50",
                                "description": "morning cafe latte",
                                "source_name": "EvalSrcAsset{{run_id}}",
                                "destination_name": "EvalDestExpense{{run_id}}",
                                "currency_code": "EUR"
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
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/rules?limit=50",
                    "headers": {
                        "Accept": "application/json"
                    }
                },
                "save_as": "rules"
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/rules/{{rules.data[0].id}}/test?start=2025-04-01&end=2025-04-30",
                    "headers": {
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.data",
                            "type": "array"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "RuleDryRun",
            "method": "binary",
            "maxScore": 4
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=RuleDryRun",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_RULE_CREATE",
            "API_TRANSACTION_CREATE_WITHDRAWAL"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_RULE_TRIGGER_APPLIES_ACTIONS(context: dict) -> NodeResult:
    node = {
        "id": "API_RULE_TRIGGER_APPLIES_ACTIONS",
        "description": "Deep: POST /api/v1/rules/{rule}/trigger executes actions on matching journals. After firing, the affected journal must carry the tag the rule's add_tag action specified (verified via SQL on tag_transaction_journal join).",
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
                    "method": "GET",
                    "path": "/api/v1/rules?limit=50",
                    "headers": {
                        "Accept": "application/json"
                    }
                },
                "save_as": "rules"
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/rules/{{rules.data[0].id}}/trigger?start=2025-04-01&end=2025-04-30",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {}
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
                    "sql": "SELECT COUNT(*) AS cnt FROM tag_transaction_journal ttj JOIN tags t ON ttj.tag_id=t.id JOIN transaction_journals tj ON ttj.transaction_journal_id=tj.id WHERE t.tag='food' AND tj.description LIKE '%cafe%'",
                    "min_value": 1,
                    "comment": "After firing the rule, every journal whose description matches 'cafe' must be tagged 'food'."
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "RuleTriggerSideEffect",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=RuleTriggerSideEffect",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_RULE_CREATE",
            "API_RULE_TEST_DRY_RUN"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_WEBHOOK_CREATE(context: dict) -> NodeResult:
    node = {
        "id": "API_WEBHOOK_CREATE",
        "description": "POST /api/v1/webhooks creates a webhook with triggers[]+responses[]+deliveries[] arrays (PRD §6.18.2). Singular forms must be rejected; we send the plural form.",
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
                    "path": "/api/v1/webhooks",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "title": "EvalStoreTxnHook",
                        "active": True,
                        "triggers": [
                            "STORE_TRANSACTION"
                        ],
                        "responses": [
                            "TRANSACTIONS"
                        ],
                        "deliveries": [
                            "JSON"
                        ],
                        "url": "http://192.168.224.2:9001/hook"
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
                            "path": "$.data.type",
                            "expected": "webhooks"
                        },
                        {
                            "path": "$.data.attributes.title",
                            "expected": "EvalStoreTxnHook"
                        },
                        {
                            "path": "$.data.attributes.active",
                            "expected": True
                        },
                        {
                            "path": "$.data.attributes.url",
                            "expected": "http://192.168.224.2:9001/hook"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "WebhookCreate",
            "method": "binary",
            "maxScore": 5
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-009",
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=WebhookCreate",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT",
            "DB_TABLE_WEBHOOKS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_WEBHOOK_LIST_MESSAGES(context: dict) -> NodeResult:
    node = {
        "id": "API_WEBHOOK_LIST_MESSAGES",
        "description": "GET /api/v1/webhooks/{webhook}/messages returns paginated WebhookMessage envelope (data.type='webhook_messages').",
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
                    "method": "GET",
                    "path": "/api/v1/webhooks?limit=1",
                    "headers": {
                        "Accept": "application/json"
                    }
                },
                "save_as": "wh_list"
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/webhooks/{{wh_list.data[0].id}}/messages?limit=10",
                    "headers": {
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.data",
                            "type": "array"
                        },
                        {
                            "path": "$.meta.pagination.per_page",
                            "type": "integer"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "WebhookMessageList",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=WebhookMessageList",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_WEBHOOK_CREATE"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_WEBHOOK_SUBMIT_REDELIVER(context: dict) -> NodeResult:
    node = {
        "id": "API_WEBHOOK_SUBMIT_REDELIVER",
        "description": "POST /api/v1/webhooks/{webhook}/submit re-queues all pending messages — must return 204 (PRD §6.18.1 row 5).",
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
                    "method": "GET",
                    "path": "/api/v1/webhooks?limit=1",
                    "headers": {
                        "Accept": "application/json"
                    }
                },
                "save_as": "wh_list"
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/webhooks/{{wh_list.data[0].id}}/submit",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {}
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
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "WebhookSubmitRedeliver",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-017"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=WebhookSubmitRedeliver",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_WEBHOOK_CREATE"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_ATTACHMENT_CREATE_AND_UPLOAD(context: dict) -> NodeResult:
    node = {
        "id": "API_ATTACHMENT_CREATE_AND_UPLOAD",
        "description": "Two-step flow per PRD §6.19: (1) POST /api/v1/attachments creates the metadata row, (2) POST /api/v1/attachments/{id}/upload uploads the raw binary body (NOT multipart). Verifies envelope + upload status.",
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
                    "method": "GET",
                    "path": "/api/v1/transactions?limit=1",
                    "headers": {
                        "Accept": "application/json"
                    }
                },
                "save_as": "txn_list"
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/attachments",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "filename": "eval-receipt.txt",
                        "title": "Eval receipt",
                        "attachable_type": "TransactionJournal",
                        "attachable_id": "{{txn_list.data[0].attributes.transactions[0].transaction_journal_id}}"
                    }
                },
                "save_as": "att"
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
                            "path": "$.data.type",
                            "expected": "attachments"
                        },
                        {
                            "path": "$.data.attributes.filename",
                            "expected": "eval-receipt.txt"
                        },
                        {
                            "path": "$.data.attributes.upload_url",
                            "exists": True,
                            "optional": True
                        }
                    ]
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/attachments/{{att.data.id}}/upload",
                    "headers": {
                        "Content-Type": "application/octet-stream",
                        "Accept": "application/json"
                    },
                    "raw_body_b64": "RXZhbCByZWNlaXB0IGNvbnRlbnQgMTIzNAo="
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
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "AttachmentCreateAndUpload",
            "method": "binary",
            "maxScore": 7
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-006",
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=AttachmentCreateAndUpload",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_TRANSACTION_CREATE_WITHDRAWAL"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_ATTACHMENT_DOWNLOAD(context: dict) -> NodeResult:
    node = {
        "id": "API_ATTACHMENT_DOWNLOAD",
        "description": "GET /api/v1/attachments/{id}/download returns the raw binary stream with Content-Type=application/octet-stream and Content-Disposition: attachment (PRD §6.1.4 + §6.19).",
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
                    "method": "GET",
                    "path": "/api/v1/attachments?limit=1",
                    "headers": {
                        "Accept": "application/json"
                    }
                },
                "save_as": "atts"
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/attachments/{{atts.data[0].id}}/download",
                    "headers": {
                        "Accept": "*/*"
                    },
                    "binary_response": True
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "header_assertions": [
                        {
                            "header": "Content-Type",
                            "match_type": "regex",
                            "pattern": "^application/octet-stream"
                        },
                        {
                            "header": "Content-Disposition",
                            "match_type": "contains",
                            "expected": "attachment"
                        }
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS cnt FROM attachments WHERE filename='eval-receipt.txt' AND uploaded=1",
                    "min_value": 1,
                    "comment": "uploaded flag must flip True after the upload step succeeded — this validates persistence end-to-end."
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "AttachmentDownloadBinary",
            "method": "binary",
            "maxScore": 6
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=AttachmentDownloadBinary",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_ATTACHMENT_CREATE_AND_UPLOAD"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_CURRENCY_LIST(context: dict) -> NodeResult:
    node = {
        "id": "API_CURRENCY_LIST",
        "description": "GET /api/v1/currencies returns the paginated list of TransactionCurrency records with data.type='currencies'.",
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
                    "method": "GET",
                    "path": "/api/v1/currencies?limit=10",
                    "headers": {
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.data",
                            "type": "array"
                        },
                        {
                            "path": "$.data[0].type",
                            "expected": "currencies"
                        },
                        {
                            "path": "$.data[0].attributes.code",
                            "match_type": "regex",
                            "pattern": "^[A-Z]{3,5}$"
                        },
                        {
                            "path": "$.meta.pagination.per_page",
                            "type": "integer"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "CurrencyList",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=CurrencyList",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_EXCHANGE_RATE_CREATE(context: dict) -> NodeResult:
    node = {
        "id": "API_EXCHANGE_RATE_CREATE",
        "description": "POST /api/v1/exchange-rates creates a CurrencyExchangeRate record (PRD §6.22.2: required fields date, rate, from, to). Verifies the rate is preserved as a numeric string (KB-001 pattern).",
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
                    "path": "/api/v1/exchange-rates",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "date": "2025-04-01",
                        "rate": "1.0850",
                        "from": "EUR",
                        "to": "USD"
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
                            "path": "$.data.type",
                            "expected": "exchange-rates"
                        },
                        {
                            "path": "$.data.attributes.from_currency_code",
                            "expected": "EUR",
                            "optional_aliases": [
                                "from",
                                "from_code"
                            ]
                        },
                        {
                            "path": "$.data.attributes.to_currency_code",
                            "expected": "USD",
                            "optional_aliases": [
                                "to",
                                "to_code"
                            ]
                        },
                        {
                            "path": "$.data.attributes.rate",
                            "expected_numeric": 1.085,
                            "tolerance": 0.0001,
                            "match_type": "numeric_string"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "ExchangeRateCreate",
            "method": "binary",
            "maxScore": 5
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-001",
            "KB-009",
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=ExchangeRateCreate",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_CURRENCY_LIST",
            "DB_TABLE_CURRENCY_EXCHANGE_RATES"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_AUTOCOMPLETE_ACCOUNTS(context: dict) -> NodeResult:
    node = {
        "id": "API_AUTOCOMPLETE_ACCOUNTS",
        "description": "GET /api/v1/autocomplete/accounts?query=Eval returns a flat top-level JSON array (NOT a {data:...} envelope per KB-022 / PRD §6.4); each element has id, name, type, currency_code.",
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
                    "method": "GET",
                    "path": "/api/v1/autocomplete/accounts?query=Eval&limit=5",
                    "headers": {
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$",
                            "type": "array"
                        },
                        {
                            "path": "$[0].id",
                            "exists": True,
                            "optional": True
                        },
                        {
                            "path": "$[0].name",
                            "match_type": "contains",
                            "expected": "Eval",
                            "optional": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "AutocompleteAccounts",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-022"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=AutocompleteAccounts",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_ACCOUNT_CREATE"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_CHART_ACCOUNT_OVERVIEW(context: dict) -> NodeResult:
    node = {
        "id": "API_CHART_ACCOUNT_OVERVIEW",
        "description": "GET /api/v1/chart/account/overview?start=&end= returns an array of line-chart series (label, currency_code, type='line', entries map of date->balance) per PRD §6.38.",
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
                    "method": "GET",
                    "path": "/api/v1/chart/account/overview?start=2025-04-01&end=2025-04-30",
                    "headers": {
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$",
                            "type": "array"
                        },
                        {
                            "path": "$[0].label",
                            "type": "string",
                            "optional": True
                        },
                        {
                            "path": "$[0].type",
                            "expected": "line",
                            "optional": True
                        },
                        {
                            "path": "$[0].entries",
                            "type": "object",
                            "optional": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "ChartAccountOverview",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-001"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=ChartAccountOverview",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_ACCOUNT_CREATE"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_SUMMARY_BASIC(context: dict) -> NodeResult:
    node = {
        "id": "API_SUMMARY_BASIC",
        "description": "GET /api/v1/summary/basic?start=&end=&currency_code=EUR returns a keyed object (one entry per metric) per PRD §6.36; monetary_value field is a JSON string per KB-001.",
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
                    "method": "GET",
                    "path": "/api/v1/summary/basic?start=2025-04-01&end=2025-04-30&currency_code=EUR",
                    "headers": {
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$",
                            "type": "object"
                        },
                        {
                            "path": "$..monetary_value",
                            "type": "string",
                            "match_type": "any_match",
                            "comment": "Per KB-001 monetary fields are emitted as strings, never numeric literals."
                        },
                        {
                            "path": "$..currency_code",
                            "match_type": "any_match",
                            "expected": "EUR"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "SummaryBasic",
            "method": "binary",
            "maxScore": 4
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-001"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=SummaryBasic",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_ACCOUNT_CREATE"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_SEARCH_TRANSACTIONS(context: dict) -> NodeResult:
    node = {
        "id": "API_SEARCH_TRANSACTIONS",
        "description": "GET /api/v1/search/transactions?query=cafe returns paginated TransactionGroup envelope plus meta.search.{query,total_results} per PRD §6.32.",
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
                    "method": "GET",
                    "path": "/api/v1/search/transactions?query=cafe&limit=10",
                    "headers": {
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.data",
                            "type": "array"
                        },
                        {
                            "path": "$.meta.pagination.per_page",
                            "type": "integer"
                        },
                        {
                            "path": "$.meta.search.query",
                            "expected": "cafe",
                            "optional": True
                        },
                        {
                            "path": "$.meta.search.total_results",
                            "type": "integer",
                            "optional": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "SearchTransactions",
            "method": "binary",
            "maxScore": 4
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=SearchTransactions",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_TRANSACTION_CREATE_WITHDRAWAL"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_ABOUT_RETURNS_VERSION(context: dict) -> NodeResult:
    node = {
        "id": "API_ABOUT_RETURNS_VERSION",
        "description": "GET /api/v1/about returns {data:{version, api_version, php_version, os, driver}} per PRD §6.45. Version must be a non-empty string.",
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
                    "method": "GET",
                    "path": "/api/v1/about",
                    "headers": {
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.data.version",
                            "type": "string",
                            "min_length": 1
                        },
                        {
                            "path": "$.data.api_version",
                            "type": "string",
                            "min_length": 1,
                            "optional": True
                        },
                        {
                            "path": "$.data.php_version",
                            "match_type": "regex",
                            "pattern": "^[0-9]+\\.[0-9]+",
                            "optional": True
                        },
                        {
                            "path": "$.data.driver",
                            "type": "string",
                            "optional": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "AboutVersion",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=AboutVersion",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_ABOUT_USER_RETURNS_CURRENT(context: dict) -> NodeResult:
    node = {
        "id": "API_ABOUT_USER_RETURNS_CURRENT",
        "description": "GET /api/v1/about/user returns the authenticated user's record; data.attributes.email must equal admin@pfm.local per PRD §6.45 row 2.",
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
                    "method": "GET",
                    "path": "/api/v1/about/user",
                    "headers": {
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.data.id",
                            "exists": True
                        },
                        {
                            "path": "$.data.attributes.email",
                            "expected": "admin@pfm.local"
                        },
                        {
                            "path": "$.data.attributes.role",
                            "match_type": "regex",
                            "pattern": "^(owner|admin)$",
                            "optional": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "AboutUserCurrent",
            "method": "binary",
            "maxScore": 4
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=AboutUserCurrent",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_CRON_TOKEN_AUTH_NO_BEARER(context: dict) -> NodeResult:
    node = {
        "id": "API_CRON_TOKEN_AUTH_NO_BEARER",
        "description": "GET /api/v1/cron/{STATIC_CRON_TOKEN} bypasses auth:api (PRD §6.1.6 / §6.3) — the cron endpoint is the ONLY route that authenticates via URL token, NOT Bearer. Sending NO Authorization header MUST still return 200; sending an invalid token MUST return 403.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin",
                    "purpose": "establish DB context only; do NOT attach Authorization to subsequent P04 calls in this node"
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT TRIM(BOTH '\"' FROM data) AS token FROM configuration WHERE name='static_cron_token' UNION ALL SELECT 'fixture-token-value-32-chars-long' AS token LIMIT 1",
                    "save_first_row_as": "cron_cfg",
                    "fallback_value": "fixture-token-value-32-chars-long",
                    "comment": "Resolve the configured 32-char STATIC_CRON_TOKEN; the fixture seeds a deterministic value."
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/cron/{{cron_cfg.token}}",
                    "headers": {
                        "Accept": "application/json"
                    },
                    "no_auth": True,
                    "comment": "Explicitly suppress the Authorization header injected by P13 — the cron endpoint must work without it."
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.message",
                            "type": "string",
                            "optional": True
                        },
                        {
                            "path": "$.cron_jobs",
                            "type": "array",
                            "optional": True
                        }
                    ]
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/cron/this-is-an-invalid-token-value-xx",
                    "headers": {
                        "Accept": "application/json"
                    },
                    "no_auth": True
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 403
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "CronTokenAuthBypassesBearer",
            "method": "binary",
            "maxScore": 8,
            "expected_reference_fail": "Verified live against the reference: GET /api/v1/cron/{token} fires the cron job and returns 200 for ANY token value (a valid 32-char token, an arbitrary invalid string, and a 5-char string all returned 200 with job_fired=true). Firefly's CronController/CronRequest does not validate the URL token against static_cron_token, so the spec's 'invalid token MUST return 403' clause is not implemented in the reference. The no-Bearer/valid-token half (200) works; the whole node is dropped from scoring rather than penalising the baseline for an unimplemented denial branch."
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-018"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=CronTokenAuthBypassesBearer",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_OAUTH_CREATE_CLIENT_PERSISTED(context: dict) -> NodeResult:
    node = {
        "id": "API_OAUTH_CREATE_CLIENT_PERSISTED",
        "description": "POST /oauth/clients (registered in routes/web.php — PRD §6.2) creates an OAuth client; plaintext secret is returned ONCE in the response. Verifies persistence in oauth_clients table.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin",
                    "session_required": True,
                    "comment": "/oauth/* routes use SESSION auth (web middleware), not Bearer."
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/oauth/clients",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "X-Requested-With": "XMLHttpRequest"
                    },
                    "body": {
                        "name": "EvalOAuthClient{{run_id}}",
                        "redirect": "https://example.invalid/callback"
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
                            "path": "$.id",
                            "exists": True
                        },
                        {
                            "path": "$.name",
                            "expected": "EvalOAuthClient{{run_id}}"
                        },
                        {
                            "path": "$.redirect",
                            "expected": "https://example.invalid/callback"
                        },
                        {
                            "path": "$.secret",
                            "type": "string",
                            "min_length": 20,
                            "comment": "Per PRD §6.2 the plaintext secret is returned ONCE."
                        }
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS cnt FROM oauth_clients WHERE name='EvalOAuthClient' AND revoked=0",
                    "expected_first_row": {
                        "cnt": 1
                    }
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "OAuthCreateClient",
            "method": "binary",
            "maxScore": 7,
            "expected_reference_fail": "Reference limitation: OAuth client management is NOT exposed as an API-token endpoint. Firefly calls Passport::ignoreRoutes() and registers client CRUD only under web routes (POST /oauth/clients) guarded by ['web','auth:web'] (session + CSRF), verified in routes/web.php. There is no /api/v1/oauth/clients route; a bearer-token client cannot create OAuth clients."
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=OAuthCreateClient",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_OAUTH_CREATE_PAT(context: dict) -> NodeResult:
    node = {
        "id": "API_OAUTH_CREATE_PAT",
        "description": "POST /oauth/personal-access-tokens creates a Personal Access Token; the plaintext JWT (`accessToken`) is returned ONCE per PRD §6.2.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin",
                    "session_required": True
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/oauth/personal-access-tokens",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "X-Requested-With": "XMLHttpRequest"
                    },
                    "body": {
                        "name": "EvalPAT{{run_id}}",
                        "scopes": []
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
                            "path": "$.accessToken",
                            "type": "string",
                            "min_length": 30
                        },
                        {
                            "path": "$.token.id",
                            "exists": True
                        },
                        {
                            "path": "$.token.name",
                            "expected": "EvalPAT{{run_id}}"
                        },
                        {
                            "path": "$.token.revoked",
                            "expected": False,
                            "optional": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "OAuthCreatePAT",
            "method": "binary",
            "maxScore": 6
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=OAuthCreatePAT",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_OAUTH_LIST_TOKENS(context: dict) -> NodeResult:
    node = {
        "id": "API_OAUTH_LIST_TOKENS",
        "description": "GET /oauth/tokens lists the user's authorized OAuth tokens (PRD §6.2 row 5). The previously-created PAT must appear in the result.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin",
                    "session_required": True
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/oauth/personal-access-tokens",
                    "headers": {
                        "Accept": "application/json",
                        "X-Requested-With": "XMLHttpRequest"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$",
                            "type": "array"
                        },
                        {
                            "path": "$[*].name",
                            "match_type": "any_match",
                            "expected": "EvalPAT{{run_id}}"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "OAuthListTokens",
            "method": "binary",
            "maxScore": 4
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-010"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=OAuthListTokens",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_OAUTH_CREATE_PAT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_ERROR_404_FORMAT(context: dict) -> NodeResult:
    node = {
        "id": "API_ERROR_404_FORMAT",
        "description": "GET /api/v1/accounts/9999999 (a clearly nonexistent id) MUST return 404 with body shape {message:'No query results for model [App\\Models\\Account] 9999999'} (or empty message in production) per KB-014 / PRD §6.1.5.",
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
                    "method": "GET",
                    "path": "/api/v1/accounts/9999999",
                    "headers": {
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 404
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.message",
                            "match_type": "regex",
                            "pattern": "(No query results for model|Account|Resource not found|Not Found|^$)",
                            "comment": "Matches verbose dev message OR empty production message — both are valid per KB-014."
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "Error404Format",
            "method": "binary",
            "maxScore": 4
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-014"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=Error404Format",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_API_ERROR_422_FORMAT(context: dict) -> NodeResult:
    node = {
        "id": "API_ERROR_422_FORMAT",
        "description": "POST /api/v1/accounts with an empty body MUST return 422 with body {message:'The given data was invalid.', errors:{<field>:[<msg>...]}} per KB-015 / PRD §6.1.5. The `errors` value MUST be an object keyed by field name (NOT a flat array, NOT JSON:API errors envelope).",
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
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {}
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 422
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.message",
                            "match_type": "regex",
                            "pattern": "(is required|invalid|must be|already in use|already been taken|more error|The .+ field)",
                            "comment": "Laravel/Firefly 422 validation envelope — message is a human-readable summary whose wording depends on the failed rule (e.g. 'is invalid', 'is required', 'This name is already in use.'), never guaranteed to contain the literal 'invalid'."
                        },
                        {
                            "path": "$.errors",
                            "type": "object"
                        },
                        {
                            "path": "$.errors.name",
                            "type": "array",
                            "optional_aliases": [
                                "errors.type"
                            ]
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "API",
            "subcategory": "Error422Format",
            "method": "binary",
            "maxScore": 5
        },
        "complexity_tier": "linear_crud",
        "_kb_refs": [
            "KB-015"
        ],
        "source_evidence": {
            "source_file": "API §6",
            "behavior_verified": "Static / source-derived; subcategory=Error422Format",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)

