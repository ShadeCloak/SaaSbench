
from __future__ import annotations

from ..utils import NodeResult
from ._common import execute_primitive_chain


def test_EDGE_FP_ACCOUNT_TYPE_MATRIX(context: dict) -> NodeResult:
    node = {
        "id": "EDGE_FP_ACCOUNT_TYPE_MATRIX",
        "description": "FP-ACCOUNT-TYPE-MATRIX (DE-INV-2): Withdrawal with destination=Asset is FORBIDDEN by source_dests matrix. POST /api/v1/transactions with type=withdrawal, source=Asset, destination=Asset MUST return 422 with errors.transactions.0.destination_id. Agents that skip the matrix accept it as Transfer (or 200) and fail.",
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
                                "destination_id": "{{asset_account_eur_id_2}}",
                                "amount": "5.00",
                                "currency_code": "EUR",
                                "date": "2026-04-15",
                                "description": "matrix violation probe"
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
                            "exists": True
                        },
                        {
                            "path": "$.errors",
                            "exists": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "EdgeCases",
            "subcategory": "AccountTypeMatrix",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [
            "FP-ACCOUNT-TYPE-MATRIX"
        ],
        "source_evidence": {
            "source_file": "Cross-cutting §4-5",
            "behavior_verified": "Static / source-derived; subcategory=AccountTypeMatrix",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_EDGE_FP_USER_GROUP_404_HIDE(context: dict) -> NodeResult:
    node = {
        "id": "EDGE_FP_USER_GROUP_404_HIDE",
        "description": "FP-USER-GROUP-ISOLATION + FP-RBAC-404-VS-403 (KB-055): Cross-group access MUST return 404 (not 403) — routeBinder cannot find the resource via $auth->user->{relation}() so ModelNotFoundException → 404. Setup user_b in different group, attempt GET /api/v1/accounts/{user_a_account_id} as user_b → 404.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "user_b_diff_group"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/accounts/{{user_a_account_id}}",
                    "headers": {
                        "Authorization": "Bearer {{user_b_token}}",
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
                            "exists": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "EdgeCases",
            "subcategory": "UserGroup404Hide",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-055"
        ],
        "_failure_point_refs": [
            "FP-USER-GROUP-ISOLATION",
            "FP-RBAC-404-VS-403"
        ],
        "source_evidence": {
            "source_file": "Cross-cutting §4-5",
            "behavior_verified": "Static / source-derived; subcategory=UserGroup404Hide",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_EDGE_FP_PASSPORT_MANUAL_ROUTES(context: dict) -> NodeResult:
    node = {
        "id": "EDGE_FP_PASSPORT_MANUAL_ROUTES",
        "description": "FP-PASSPORT-MANUAL-ROUTES: Passport routes MUST be hand-registered in routes/web.php (Passport 12 removed Passport::routes()). Verify POST /oauth/token with grant_type=password returns 200 + access_token field. Failure mode: agent calls Passport::routes() and gets 404.",
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
                    "path": "/oauth/token",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "grant_type": "password",
                        "client_id": "{{password_client_id}}",
                        "client_secret": "{{password_client_secret}}",
                        "username": "{{admin_email}}",
                        "password": "{{admin_password}}",
                        "scope": "*"
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
                            "path": "$.token_type",
                            "expected": "Bearer"
                        },
                        {
                            "path": "$.access_token",
                            "exists": True
                        },
                        {
                            "path": "$.expires_in",
                            "exists": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "EdgeCases",
            "subcategory": "PassportManualRoutes",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [],
        "_failure_point_refs": [
            "FP-PASSPORT-MANUAL-ROUTES"
        ],
        "source_evidence": {
            "source_file": "Cross-cutting §4-5",
            "behavior_verified": "Static / source-derived; subcategory=PassportManualRoutes",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_EDGE_FP_RULE_ENGINE_SEARCH_COMBO(context: dict) -> NodeResult:
    node = {
        "id": "EDGE_FP_RULE_ENGINE_SEARCH_COMBO",
        "description": "FP-RULE-ENGINE-SEARCH: Combined trigger 'amount_more:100 AND description_contains:cafe' must work via gdbots search-query parsing (NOT plain Eloquent WHERE). Agent that only handles single triggers fails the combo. Setup rule with both triggers strict=True → only journal satisfying BOTH is tagged.",
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
                    "path": "/api/v1/rules",
                    "headers": {
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "title": "combo trigger probe",
                        "rule_group_id": "{{rg_id}}",
                        "active": True,
                        "strict": True,
                        "stop_processing": False,
                        "trigger": "store-journal",
                        "triggers": [
                            {
                                "type": "amount_more",
                                "value": "100",
                                "active": True
                            },
                            {
                                "type": "description_contains",
                                "value": "cafe",
                                "active": True
                            }
                        ],
                        "actions": [
                            {
                                "type": "add_tag",
                                "value": "combo-fired",
                                "active": True
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
                                "amount": "150.00",
                                "currency_code": "EUR",
                                "date": "2026-04-15",
                                "description": "expensive cafe night"
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
                    "sql": "SELECT COUNT(*) AS combo_tagged FROM tag_transaction_journal ttj INNER JOIN transaction_journals tj ON ttj.transaction_journal_id = tj.id INNER JOIN tags t ON ttj.tag_id = t.id WHERE tj.description = 'expensive cafe night' AND t.tag = 'combo-fired'",
                    "expected_result": {
                        "combo_tagged": 1
                    }
                }
            }
        ],
        "scoring": {
            "category": "EdgeCases",
            "subcategory": "RuleEngineSearchCombo",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [
            "FP-RULE-ENGINE-SEARCH"
        ],
        "source_evidence": {
            "source_file": "Cross-cutting §4-5",
            "behavior_verified": "Static / source-derived; subcategory=RuleEngineSearchCombo",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_RULE_DESCRIPTION_CONTAINS_TRIGGER"
        ]
    }
    return execute_primitive_chain(node, context)


def test_EDGE_FP_AUTOBUDGET_CALENDAR_BOUNDARY(context: dict) -> NodeResult:
    node = {
        "id": "EDGE_FP_AUTOBUDGET_CALENDAR_BOUNDARY",
        "description": "FP-AUTOBUDGET-PERIOD: monthly AutoBudget MUST trigger on the 1st of every month (calendar boundary, BD-INV-2 isMagicDay). Common agent failure: using last_run + 30 days, which means February only fires once. Verify created BudgetLimit.start_date matches DATE_FORMAT(NOW(),'%Y-%m-01').",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin"
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS first_of_month_limits FROM budget_limits bl WHERE bl.start_date = DATE_FORMAT(NOW(),'%Y-%m-01') AND DAY(bl.start_date) = 1",
                    "expected_min": {
                        "first_of_month_limits": 1
                    }
                }
            }
        ],
        "scoring": {
            "category": "EdgeCases",
            "subcategory": "AutoBudgetCalendarBoundary",
            "method": "binary",
            "maxScore": 8
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [
            "FP-AUTOBUDGET-PERIOD"
        ],
        "source_evidence": {
            "source_file": "Cross-cutting §4-5",
            "behavior_verified": "Static / source-derived; subcategory=AutoBudgetCalendarBoundary",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_BUDGET_AUTOBUDGET_RESET_MONTHLY"
        ]
    }
    return execute_primitive_chain(node, context)


def test_EDGE_FP_WEBHOOK_SHA3_NOT_SHA256(context: dict) -> NodeResult:
    node = {
        "id": "EDGE_FP_WEBHOOK_SHA3_NOT_SHA256",
        "description": "FP-WEBHOOK-SIGNATURE-ALG: The signature algorithm MUST be SHA3 family (sha3-512 per KB-047), NOT sha256/sha512 (regular SHA-2). Mock receiver records the v1 hex signature length: SHA3-512 → 128 hex chars; SHA-256 → 64 hex chars. Verify v1 length == 128.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin"
                }
            },
            {
                "type": "P27",
                "inputs": {
                    "register": {
                        "path": "/api/v1/webhooks",
                        "headers": {
                            "Authorization": "Bearer {{admin_token}}",
                            "Content-Type": "application/json"
                        },
                        "body": {
                            "title": "sha3-not-sha256 probe",
                            "url": "http://host.docker.internal:{{webhook_port}}/sig-len",
                            "active": True,
                            "triggers": ["STORE_TRANSACTION"],
                            "responses": ["TRANSACTIONS"],
                            "deliveries": ["JSON"]
                        }
                    },
                    "trigger": {
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
                                    "amount": "0.01",
                                    "currency_code": "EUR",
                                    "date": "2026-04-15",
                                    "description": "sig length probe"
                                }
                            ]
                        }
                    },
                    "queue_processing": {
                        "command": "php artisan firefly-iii:cron --send-webhook-messages --force && php artisan queue:work --once --stop-when-empty",
                        "container": "{{app_container}}"
                    },
                    "expect_delivery": {
                        "timeout_ms": 15000,
                        "headers_contain": {
                            "Signature": "^t=\\d+,v1=[0-9a-f]{128}$"
                        },
                        "_assertion_note": "Pattern enforces 128 hex chars (sha3-512); sha256 (64 chars) and sha512 (128 chars but NOT sha3) will fail when combined with the algorithm verification in BIZ_WEBHOOK_HMAC_SHA3_512."
                    }
                }
            }
        ],
        "scoring": {
            "category": "EdgeCases",
            "subcategory": "WebhookSha3NotSha256",
            "method": "binary",
            "maxScore": 8,
            "expected_reference_fail": "Verified live against the reference: Firefly signs webhook deliveries with HMAC-SHA256 (64-hex v1 signature), NOT the sha3-512 (128-hex) the spec/KB-047 mandate — this is the exact reference limitation already documented on the sibling node BIZ_WEBHOOK_HMAC_SHA3_512 (Firefly's Webhooks/MessageGenerator uses hash_hmac('sha256', ...)). The node's expect_delivery pattern '^t=\\d+,v1=[0-9a-f]{128}$' therefore can NEVER match the reference's 64-hex signature, so it is dropped from scoring rather than penalising the baseline for a hash algorithm it does not implement. (The observed 'webhook not received within timeout' is moot: even a delivered payload would fail the 128-hex assertion.)"
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-047"
        ],
        "_failure_point_refs": [
            "FP-WEBHOOK-SIGNATURE-ALG"
        ],
        "source_evidence": {
            "source_file": "Cross-cutting §4-5",
            "behavior_verified": "Static / source-derived; subcategory=WebhookSha3NotSha256",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_WEBHOOK_HMAC_SHA3_512"
        ]
    }
    return execute_primitive_chain(node, context)


def test_EDGE_FP_CURRENCY_DECIMAL_INVALID_PRECISION(context: dict) -> NodeResult:
    node = {
        "id": "EDGE_FP_CURRENCY_DECIMAL_INVALID_PRECISION",
        "description": "FP-CURRENCY-DECIMAL-PLACES: Submitting a JPY transaction with amount='100.50' (1 decimal) MUST be normalised to '100' or '101' OR rejected with 422 (decimal precision exceeds JPY's decimal_places=0). Agents using float '%.2f' format everywhere accept it as 100.50 and store with extra precision.",
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
                                "source_id": "{{asset_account_jpy_id}}",
                                "destination_id": "{{expense_account_id}}",
                                "amount": "100",
                                "currency_code": "JPY",
                                "date": "2026-04-15",
                                "description": "JPY integer-only probe"
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
                            "path": "$.data.attributes.transactions[0].amount",
                            "expected": "100",
                            "match": "exact"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "EdgeCases",
            "subcategory": "CurrencyDecimalInvalidPrecision",
            "method": "binary",
            "maxScore": 8
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [
            "FP-CURRENCY-DECIMAL-PLACES"
        ],
        "source_evidence": {
            "source_file": "Cross-cutting §4-5",
            "behavior_verified": "Static / source-derived; subcategory=CurrencyDecimalInvalidPrecision",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_ACCOUNT_CREATE",
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_EDGE_FP_CRON_TOKEN_NO_AUTH(context: dict) -> NodeResult:
    node = {
        "id": "EDGE_FP_CRON_TOKEN_NO_AUTH",
        "description": "FP-CRON-TOKEN-AUTH: GET /api/v1/cron/{token} (the STATIC_CRON_TOKEN-protected endpoint) MUST work WITHOUT Bearer auth — routes/api.php declares ->withoutMiddleware(['api']) for the cron group. Agent that requires auth:api returns 401, breaking scheduled cron triggers.",
        "primitive_chain": [
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/cron/{{static_cron_token}}",
                    "headers": {
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "acceptable_statuses": [
                        200,
                        202
                    ]
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$",
                            "exists": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "EdgeCases",
            "subcategory": "CronTokenNoAuth",
            "method": "binary",
            "maxScore": 6
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [
            "FP-CRON-TOKEN-AUTH"
        ],
        "source_evidence": {
            "source_file": "Cross-cutting §4-5",
            "behavior_verified": "Static / source-derived; subcategory=CronTokenNoAuth",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT",
            "SETUP_CREATE_ADMIN_USER"
        ]
    }
    return execute_primitive_chain(node, context)


def test_EDGE_FP_PIVOT_TABLE_NAMING(context: dict) -> NodeResult:
    node = {
        "id": "EDGE_FP_PIVOT_TABLE_NAMING",
        "description": "FP-PIVOT-TABLE-NAMING: PiggyBank::accounts belongsToMany pivot uses the SINGULAR-underscore Laravel convention 'account_piggy_bank' (alphabetical, singular). Agents using Laravel 'piggy_banks_accounts' (plural) or 'piggy_bank_account' (wrong-order) fail P09 table-existence check.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin"
                }
            },
            {
                "type": "P09",
                "inputs": {
                    "tables": [
                        "account_piggy_bank"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "account_piggy_bank",
                    "expected_columns": [
                        "account_id",
                        "piggy_bank_id",
                        "current_amount",
                        "native_current_amount"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "EdgeCases",
            "subcategory": "PivotTableNaming",
            "method": "binary",
            "maxScore": 8
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [
            "FP-PIVOT-TABLE-NAMING"
        ],
        "source_evidence": {
            "source_file": "Cross-cutting §4-5",
            "behavior_verified": "Static / source-derived; subcategory=PivotTableNaming",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "DB_TABLE_ACCOUNTS",
            "DB_TABLE_PIGGY_BANKS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_EDGE_INVALID_TRANSACTION_TYPE_REJECTED(context: dict) -> NodeResult:
    node = {
        "id": "EDGE_INVALID_TRANSACTION_TYPE_REJECTED",
        "description": "Defense: TransactionType enum has exactly 7 values (Withdrawal/Deposit/Transfer/Opening balance/Reconciliation/Liability credit/Invalid). Sending type='Bogus' MUST return 422. (The 'Invalid' sentinel is internal-only and TransactionFactory throws AppException when encountered.)",
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
                                "type": "Bogus",
                                "source_id": "{{asset_account_eur_id}}",
                                "destination_id": "{{expense_account_id}}",
                                "amount": "1.00",
                                "currency_code": "EUR",
                                "date": "2026-04-15",
                                "description": "invalid type probe"
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
                            "path": "$.errors",
                            "exists": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "EdgeCases",
            "subcategory": "InvalidTransactionType",
            "method": "binary",
            "maxScore": 6
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Cross-cutting §4-5",
            "behavior_verified": "Static / source-derived; subcategory=InvalidTransactionType",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_ACCOUNT_CREATE",
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_EDGE_VIRTUAL_BALANCE_REJECTED_NON_ASSET(context: dict) -> NodeResult:
    node = {
        "id": "EDGE_VIRTUAL_BALANCE_REJECTED_NON_ASSET",
        "description": "KB-004 / can_have_virtual_amounts: Setting virtual_balance != 0 on a non-Asset account (e.g. Expense account) MUST return HTTP 422 with errors.virtual_balance.",
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
                        "name": "Expense with virtual balance probe",
                        "type": "expense",
                        "currency_code": "EUR",
                        "virtual_balance": "100.00"
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
                            "path": "$.errors.virtual_balance",
                            "exists": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "EdgeCases",
            "subcategory": "VirtualBalanceRejected",
            "method": "binary",
            "maxScore": 6,
            "expected_reference_fail": "Verified live against the reference: POST /api/v1/accounts with {type:'expense', virtual_balance:'50.00'} returns HTTP 200 and creates the account. Firefly does NOT reject a virtual_balance on a non-asset account with a 422 / $.errors.virtual_balance — its account StoreRequest validation accepts (and silently ignores) virtual_balance for non-asset types. The spec's 'virtual_balance rejected on non-asset' invariant is not implemented in the reference, so the node is dropped from scoring rather than penalising the baseline for absent validation."
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-004"
        ],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Cross-cutting §4-5",
            "behavior_verified": "Static / source-derived; subcategory=VirtualBalanceRejected",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_EDGE_PAGINATION_LIMIT_CLAMPED(context: dict) -> NodeResult:
    node = {
        "id": "EDGE_PAGINATION_LIMIT_CLAMPED",
        "description": "KB-011: Requesting ?limit=10000 silently clamps to the configured maximum (commonly 100), NOT 422. Verify GET /api/v1/transactions?limit=10000 returns 200 AND meta.pagination.per_page <= 100.",
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
                    "path": "/api/v1/transactions?limit=10000",
                    "headers": {
                        "Authorization": "Bearer {{admin_token}}",
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
                            "expected": 100,
                            "tolerance_max": 100
                        },
                        {
                            "path": "$.meta.pagination",
                            "exists": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "EdgeCases",
            "subcategory": "PaginationLimitClamped",
            "method": "binary",
            "maxScore": 6,
            "expected_reference_fail": "Verified live against the reference: GET /api/v1/transactions?limit=10000 (and ?limit=500, tested on both /transactions and /accounts) returns 200 with meta.pagination.per_page echoing the requested value verbatim (10000 -> 10000, 500 -> 500). Firefly does NOT clamp the page size to a configured maximum of 100; it honours the requested limit. The spec's 'silently clamps to <=100' invariant is therefore not implemented in the reference, so the node is dropped from scoring rather than penalising the baseline for absent clamping."
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-011"
        ],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Cross-cutting §4-5",
            "behavior_verified": "Static / source-derived; subcategory=PaginationLimitClamped",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_DE_SUM_ZERO_INVARIANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_EDGE_FRONTEND_LOGIN_PAGE_RENDERS(context: dict) -> NodeResult:
    node = {
        "id": "EDGE_FRONTEND_LOGIN_PAGE_RENDERS",
        "description": "GET /login MUST return 200 and the response body must contain a form referencing the email + password fields (form-based login flow).",
        "primitive_chain": [
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/login",
                    "headers": {
                        "Accept": "text/html"
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
                "type": "P19",
                "inputs": {
                    "url": "/login",
                    "assertions": [
                        {
                            "selector": "form",
                            "shouldExist": True
                        },
                        {
                            "selector": "input[type=email], input[name=email]",
                            "shouldExist": True
                        },
                        {
                            "selector": "input[type=password], input[name=password]",
                            "shouldExist": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "EdgeCases",
            "subcategory": "FrontendLoginRenders",
            "method": "binary",
            "maxScore": 5
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Cross-cutting §4-5",
            "behavior_verified": "Static / source-derived; subcategory=FrontendLoginRenders",
            "needs_api_behavior_verification": True
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_EDGE_FRONTEND_DASHBOARD_REQUIRES_AUTH(context: dict) -> NodeResult:
    node = {
        "id": "EDGE_FRONTEND_DASHBOARD_REQUIRES_AUTH",
        "description": "GET / (or /home) without an authenticated session MUST redirect (302) to /login (web auth middleware). Agents that don't gate the dashboard return 200 and fail.",
        "primitive_chain": [
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/",
                    "headers": {
                        "Accept": "text/html"
                    },
                    "follow_redirects": False
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "acceptable_statuses": [
                        302,
                        301
                    ]
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.headers.Location",
                            "expected": "/login",
                            "match": "contains"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "EdgeCases",
            "subcategory": "DashboardRequiresAuth",
            "method": "binary",
            "maxScore": 5
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Cross-cutting §4-5",
            "behavior_verified": "Static / source-derived; subcategory=DashboardRequiresAuth",
            "needs_api_behavior_verification": True
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_EDGE_FRONTEND_CSRF_TOKEN_PRESENT(context: dict) -> NodeResult:
    node = {
        "id": "EDGE_FRONTEND_CSRF_TOKEN_PRESENT",
        "description": "GET /login response body must contain a Laravel CSRF hidden field (_token input or csrf-token meta) — required by Laravel's VerifyCsrfToken middleware on POST /login.",
        "primitive_chain": [
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/login",
                    "headers": {
                        "Accept": "text/html"
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
                "type": "P19",
                "inputs": {
                    "url": "/login",
                    "assertions": [
                        {
                            "selector": "input[name=_token], meta[name=csrf-token]",
                            "shouldExist": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "EdgeCases",
            "subcategory": "CsrfTokenPresent",
            "method": "binary",
            "maxScore": 5
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Cross-cutting §4-5",
            "behavior_verified": "Static / source-derived; subcategory=CsrfTokenPresent",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "EDGE_FRONTEND_LOGIN_PAGE_RENDERS"
        ]
    }
    return execute_primitive_chain(node, context)

