
from __future__ import annotations

from ..utils import NodeResult
from ._common import execute_primitive_chain


def test_BIZ_MC_DECIMAL_PLACES_JPY(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_MC_DECIMAL_PLACES_JPY",
        "description": "MC-INV-1 / FP-CURRENCY-DECIMAL-PLACES: JPY has decimal_places=0. Create a Withdrawal in JPY with amount='1234' → P07 assert API response amount = '1234' (no decimal point), and P08 assert DB stores the canonical DECIMAL(32,12) string '1234.000000000000'.",
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
                                "amount": "1234",
                                "date": "2026-04-07",
                                "description": "JPY decimal_places probe",
                                "currency_code": "JPY"
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
                            "expected": "1234",
                            "match": "exact"
                        },
                        {
                            "path": "$.data.attributes.transactions[0].currency_code",
                            "expected": "JPY"
                        },
                        {
                            "path": "$.data.attributes.transactions[0].currency_decimal_places",
                            "expected": 0
                        }
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT CAST(MAX(t.amount) AS CHAR) AS db_amount FROM transactions t INNER JOIN transaction_journals tj ON t.transaction_journal_id = tj.id WHERE tj.description = 'JPY decimal_places probe' AND t.deleted_at IS NULL",
                    "expected_result": {
                        "db_amount": "1234.000000000000"
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_MultiCurrency",
            "subcategory": "DecimalPlacesJPY",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-001"
        ],
        "_failure_point_refs": [
            "FP-CURRENCY-DECIMAL-PLACES"
        ],
        "source_evidence": {
            "source_file": "Business Logic §4.2",
            "behavior_verified": "Static / source-derived; subcategory=DecimalPlacesJPY",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_ACCOUNT_CREATE",
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_MC_DECIMAL_PLACES_USD_VS_BTC(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_MC_DECIMAL_PLACES_USD_VS_BTC",
        "description": "MC-INV-1: TransactionCurrency.decimal_places governs API formatting. Verify USD (decimal_places=2) emits '1234.56' and BTC (decimal_places=8) emits '0.00012345' on a paired probe. Wrong-precision agents (e.g. printf '%.2f' everywhere) fail BTC.",
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
                                "source_id": "{{asset_account_usd_id}}",
                                "destination_id": "{{expense_account_id}}",
                                "amount": "1234.56",
                                "date": "2026-04-08",
                                "description": "USD decimal_places probe",
                                "currency_code": "USD"
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
                            "expected": "1234.56",
                            "match": "exact"
                        },
                        {
                            "path": "$.data.attributes.transactions[0].currency_decimal_places",
                            "expected": 2
                        }
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
                                "source_id": "{{asset_account_btc_id}}",
                                "destination_id": "{{expense_account_id}}",
                                "amount": "0.00012345",
                                "date": "2026-04-08",
                                "description": "BTC decimal_places probe",
                                "currency_code": "BTC"
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
                            "expected": "0.00012345",
                            "match": "exact"
                        },
                        {
                            "path": "$.data.attributes.transactions[0].currency_decimal_places",
                            "expected": 8
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_MultiCurrency",
            "subcategory": "DecimalPlacesUSDvsBTC",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-001"
        ],
        "_failure_point_refs": [
            "FP-CURRENCY-DECIMAL-PLACES"
        ],
        "source_evidence": {
            "source_file": "Business Logic §4.2",
            "behavior_verified": "Static / source-derived; subcategory=DecimalPlacesUSDvsBTC",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_ACCOUNT_CREATE",
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_MC_FOREIGN_AMOUNT_DIFF_CURRENCY(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_MC_FOREIGN_AMOUNT_DIFF_CURRENCY",
        "description": "MC-INV-2: When source.currency != destination.currency (or explicit foreign_currency_id), the foreign_amount + foreign_currency_id columns MUST be populated (not NULL). Create a Transfer EUR→USD with foreign_amount='110.00' and verify both fields non-NULL in DB.",
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
                                "type": "transfer",
                                "source_id": "{{asset_account_eur_id}}",
                                "destination_id": "{{asset_account_usd_id}}",
                                "amount": "100.00",
                                "currency_code": "EUR",
                                "foreign_amount": "110.00",
                                "foreign_currency_code": "USD",
                                "date": "2026-04-09",
                                "description": "foreign_amount diff-currency probe"
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
                    "sql": "SELECT SUM(CASE WHEN t.foreign_amount IS NOT NULL THEN 1 ELSE 0 END) AS rows_with_foreign, SUM(CASE WHEN t.foreign_currency_id IS NOT NULL THEN 1 ELSE 0 END) AS rows_with_fcurrency FROM transactions t INNER JOIN transaction_journals tj ON t.transaction_journal_id = tj.id WHERE tj.description = 'foreign_amount diff-currency probe' AND t.deleted_at IS NULL",
                    "expected_result": {
                        "rows_with_foreign": 2,
                        "rows_with_fcurrency": 2
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_MultiCurrency",
            "subcategory": "ForeignAmountDiffCurrency",
            "method": "binary",
            "maxScore": 8
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-008"
        ],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §4.2",
            "behavior_verified": "Static / source-derived; subcategory=ForeignAmountDiffCurrency",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_MC_FOREIGN_AMOUNT_SAME_CURRENCY_NULL(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_MC_FOREIGN_AMOUNT_SAME_CURRENCY_NULL",
        "description": "FP-FOREIGN-AMOUNT-NULL / KB-008: When source.currency == destination.currency, foreign_amount AND foreign_currency_id MUST be NULL (not '0' or '0.00'). Common agent failure: storing 0 instead of NULL. P08 verifies IS NULL on both rows; P07 verifies API emits JSON None (key present, value None).",
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
                                "type": "transfer",
                                "source_id": "{{asset_account_eur_id}}",
                                "destination_id": "{{asset_account_eur_id_2}}",
                                "amount": "50.00",
                                "currency_code": "EUR",
                                "date": "2026-04-10",
                                "description": "foreign_amount same-currency NULL probe"
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
                        }
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT SUM(CASE WHEN t.foreign_amount IS NULL THEN 1 ELSE 0 END) AS null_foreign, SUM(CASE WHEN t.foreign_currency_id IS NULL THEN 1 ELSE 0 END) AS null_fcurrency, COUNT(*) AS total FROM transactions t INNER JOIN transaction_journals tj ON t.transaction_journal_id = tj.id WHERE tj.description = 'foreign_amount same-currency NULL probe' AND t.deleted_at IS NULL",
                    "expected_result": {
                        "null_foreign": 2,
                        "null_fcurrency": 2,
                        "total": 2
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_MultiCurrency",
            "subcategory": "ForeignAmountSameCurrencyNull",
            "method": "binary",
            "maxScore": 12
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-008"
        ],
        "_failure_point_refs": [
            "FP-FOREIGN-AMOUNT-NULL"
        ],
        "source_evidence": {
            "source_file": "Business Logic §4.2",
            "behavior_verified": "Static / source-derived; subcategory=ForeignAmountSameCurrencyNull",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_MC_EXCHANGE_RATE_CALCULATION(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_MC_EXCHANGE_RATE_CALCULATION",
        "description": "MC-INV-3: ExchangeRateConverter uses bcmath: converted = bcround(bcmul(amount, rate), to.decimal_places). Pre-seed currency_exchange_rates EUR→USD rate=1.05, then create Transfer EUR 100 → USD account WITHOUT explicit foreign_amount. The system should auto-compute foreign_amount = bcround(bcmul('100', '1.05'), 2) = '105.00'.",
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
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "from": "EUR",
                        "to": "USD",
                        "date": "2026-04-11",
                        "rate": "1.05"
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
                                "type": "transfer",
                                "source_id": "{{asset_account_eur_id}}",
                                "destination_id": "{{asset_account_usd_id}}",
                                "amount": "100.00",
                                "currency_code": "EUR",
                                "foreign_currency_code": "USD",
                                "date": "2026-04-11",
                                "description": "exchange-rate auto-compute probe"
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
                    "sql": "SELECT CAST(MAX(t.foreign_amount) AS CHAR) AS fa FROM transactions t INNER JOIN transaction_journals tj ON t.transaction_journal_id = tj.id WHERE tj.description = 'exchange-rate auto-compute probe' AND t.foreign_amount IS NOT NULL AND t.deleted_at IS NULL",
                    "expected_result": {
                        "fa": "105.000000000000"
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_MultiCurrency",
            "subcategory": "ExchangeRateCalculation",
            "method": "binary",
            "maxScore": 10,
            "expected_reference_fail": "Verified live against the reference: POST /api/v1/transactions for a foreign-currency transfer that sets foreign_currency_code but OMITS foreign_amount is rejected with 422 ('The content of this field is invalid without foreign amount information.' on transactions.0.foreign_amount / foreign_currency_id / foreign_currency_code). Firefly's StoreRequest validation does NOT auto-derive foreign_amount from the currency_exchange_rates table at store time (the ExchangeRateConverter/bcmath path is used for reporting/native-currency conversion, not for populating foreign_amount on create). The same transfer WITH an explicit foreign_amount='105.00' stores successfully. The spec's 'auto-compute foreign_amount = bcround(bcmul(amount,rate),2)' on transaction store is therefore not implemented in the reference; the node is dropped from scoring rather than penalising the baseline for an absent feature."
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §4.2",
            "behavior_verified": "Static / source-derived; subcategory=ExchangeRateCalculation",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_MC_USER_DEFAULT_CURRENCY_PIVOT(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_MC_USER_DEFAULT_CURRENCY_PIVOT",
        "description": "Per-user default currency is stored in the transaction_currency_user pivot (NOT a column on users). PUT /api/v1/preferences/currencyCode with body=USD must INSERT/UPDATE a pivot row with user_default=1 for the USD currency_id.",
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
                    "method": "PUT",
                    "path": "/api/v1/preferences/currencyCode",
                    "headers": {
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "data": "USD"
                    }
                }
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
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS default_count FROM transaction_currency_user tcu INNER JOIN transaction_currencies tc ON tcu.transaction_currency_id = tc.id INNER JOIN users u ON tcu.user_id = u.id WHERE tc.code = 'USD' AND u.email = '{{admin_email}}' AND tcu.user_default = 1",
                    "expected_result": {
                        "default_count": 1
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_MultiCurrency",
            "subcategory": "UserDefaultCurrencyPivot",
            "method": "binary",
            "maxScore": 6,
            "expected_reference_fail": "Reference limitation: the per-user default-currency pivot (transaction_currency_user.user_default) is only ever written by the one-shot upgrade command UpgradesCurrencyPreferences; there is no API path to set it. CurrencyRepository::makePrimary (invoked by POST /api/v1/currencies/{code}/primary and the redirected PUT /api/v1/preferences/currencyCode) operates on the user-group pivot (group_default), not user_default. This Firefly version replaced per-user default currency with a group-primary currency model, so the pivot assertion is unsatisfiable via API."
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §4.2",
            "behavior_verified": "Static / source-derived; subcategory=UserDefaultCurrencyPivot",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)

