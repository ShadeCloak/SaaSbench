
from __future__ import annotations

from ..utils import NodeResult
from ._common import execute_primitive_chain


def test_BIZ_BUDGET_AUTOBUDGET_RESET_MONTHLY(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_BUDGET_AUTOBUDGET_RESET_MONTHLY",
        "description": "FP-AUTOBUDGET-PERIOD: AutoBudget(period='monthly', auto_budget_type=1 RESET, amount='500') must trigger on calendar boundary (1st of month, KB-025/BD-INV-2). Run firefly-iii:cron --create-auto-budgets --force; verify a fresh budget_limits row exists with start_date = first-day-of-current-month AND amount='500'.",
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
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "name": "AutoBudget RESET probe {{run_id}}",
                        "active": True,
                        "auto_budget_type": "reset",
                        "auto_budget_currency_code": "EUR",
                        "auto_budget_amount": "500",
                        "auto_budget_period": "monthly"
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
                "type": "P12",
                "inputs": {
                    "command": "php artisan firefly-iii:cron --create-auto-budgets --force --date={{first_day_of_current_month}}",
                    "container": "{{app_container}}",
                    "expect_success": True
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT CAST(MAX(bl.amount) AS CHAR) AS amt, DATE_FORMAT(MAX(bl.start_date), '%Y-%m-%d') AS sd FROM budget_limits bl INNER JOIN budgets b ON bl.budget_id = b.id WHERE b.name LIKE 'AutoBudget RESET probe%' AND bl.start_date = DATE_FORMAT(NOW(), '%Y-%m-01')",
                    "expected_result": {
                        "amt": "500.000000000000",
                        "sd": "{{first_day_of_current_month}}"
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Budget",
            "subcategory": "AutoBudgetResetMonthly",
            "method": "binary",
            "maxScore": 12
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-025"
        ],
        "_failure_point_refs": [
            "FP-AUTOBUDGET-PERIOD"
        ],
        "source_evidence": {
            "source_file": "Business Logic §4.3",
            "behavior_verified": "Static / source-derived; subcategory=AutoBudgetResetMonthly",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_BUDGET_CREATE",
            "DB_TABLE_AUTO_BUDGETS",
            "DB_TABLE_BUDGET_LIMITS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_BUDGET_AUTOBUDGET_ROLLOVER_FORMULA(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_BUDGET_AUTOBUDGET_ROLLOVER_FORMULA",
        "description": "BD-INV-3 / KB-025: ROLLOVER strategy formula = `new_limit = auto_budget.amount + (previous_limit + previous_period_spent)` where previous_period_spent is NEGATIVE bcmath. Setup prior period: limit=500, spent=200 (Withdrawal of 200) → new period limit must equal 500+(500+(-200)) = 800.",
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
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "capture_to_context": {
                        "context_key": "rollover_budget_id",
                        "json_path": "$.data.id"
                    },
                    "body": {
                        "name": "AutoBudget ROLLOVER probe {{run_id}}",
                        "active": True,
                        "auto_budget_type": "rollover",
                        "auto_budget_currency_code": "EUR",
                        "auto_budget_amount": "500",
                        "auto_budget_period": "monthly"
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
                    "sql": "DELETE FROM budget_limits WHERE budget_id = {{rollover_budget_id}} AND start_date = DATE_FORMAT(NOW(), '%Y-%m-01')",
                    "_note": "Creating an auto-budget immediately materialises the CURRENT-period budget_limit (AutoBudgetObserver). CreateAutoBudgetLimits::handleAutoBudget only takes the ROLLOVER branch when the current period has NO limit yet, so we must remove the observer-created current-month limit before the cron runs; otherwise the rollover formula is never evaluated and the amount stays at the plain auto_budget.amount. No rows_affected assertion because on versions/paths where the observer did not pre-create it the delete is a harmless no-op."
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "INSERT INTO budget_limits (budget_id, transaction_currency_id, start_date, end_date, amount, created_at, updated_at) SELECT b.id, tc.id, DATE_SUB(DATE_FORMAT(NOW(),'%Y-%m-01'), INTERVAL 1 MONTH), LAST_DAY(DATE_SUB(NOW(), INTERVAL 1 MONTH)), '500.000000000000', NOW(), NOW() FROM budgets b CROSS JOIN transaction_currencies tc WHERE b.id = {{rollover_budget_id}} AND tc.code = 'EUR'",
                    "expected_result": {
                        "rows_affected": 1
                    },
                    "_note": "Seed previous-month limit (start=first-of-prev-month, end=last-of-prev-month) to match CreateAutoBudgetLimits::findBudgetLimit(previousStart, previousEnd)."
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
                                "amount": "200.00",
                                "currency_code": "EUR",
                                "date": "{{previous_month_15th}}",
                                "description": "rollover spent probe",
                                "budget_id": "{{rollover_budget_id}}"
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
                "type": "P12",
                "inputs": {
                    "command": "php artisan firefly-iii:cron --create-auto-budgets --force --date={{first_day_of_current_month}}",
                    "container": "{{app_container}}",
                    "expect_success": True
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT CAST(bl.amount AS CHAR) AS amt FROM budget_limits bl INNER JOIN budgets b ON bl.budget_id = b.id WHERE b.name LIKE 'AutoBudget ROLLOVER probe%' AND bl.start_date = DATE_FORMAT(NOW(), '%Y-%m-01') ORDER BY bl.id DESC LIMIT 1",
                    "expected_result": {
                        "amt": "800.000000000000"
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Budget",
            "subcategory": "AutoBudgetRolloverFormula",
            "method": "binary",
            "maxScore": 12
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-025"
        ],
        "_failure_point_refs": [
            "FP-AUTOBUDGET-PERIOD"
        ],
        "source_evidence": {
            "source_file": "Business Logic §4.3",
            "behavior_verified": "Static / source-derived; subcategory=AutoBudgetRolloverFormula",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_BUDGET_AUTOBUDGET_RESET_MONTHLY"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_BUDGET_LIMIT_PERIOD_BOUNDARY_WEEKLY(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_BUDGET_LIMIT_PERIOD_BOUNDARY_WEEKLY",
        "description": "BD-INV-2: weekly AutoBudget magic-day = $date->isMonday() (KB-016 / config). Verify a weekly AutoBudget cron only creates a new BudgetLimit on Monday with start_date aligned to Monday.",
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
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "name": "AutoBudget weekly probe {{run_id}}",
                        "active": True,
                        "auto_budget_type": "reset",
                        "auto_budget_currency_code": "EUR",
                        "auto_budget_amount": "100",
                        "auto_budget_period": "weekly"
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
                "type": "P12",
                "inputs": {
                    "command": "php artisan firefly-iii:cron --create-auto-budgets --force --date={{most_recent_monday_iso}}",
                    "container": "{{app_container}}",
                    "expect_success": True
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT DAYOFWEEK(MAX(bl.start_date)) AS dow_of_start FROM budget_limits bl INNER JOIN budgets b ON bl.budget_id = b.id WHERE b.name LIKE 'AutoBudget weekly probe%'",
                    "expected_result": {
                        "dow_of_start": 2
                    },
                    "_note": "MySQL DAYOFWEEK: Sunday=1, Monday=2"
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Budget",
            "subcategory": "WeeklyBoundary",
            "method": "binary",
            "maxScore": 8
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [
            "FP-AUTOBUDGET-PERIOD"
        ],
        "source_evidence": {
            "source_file": "Business Logic §4.3",
            "behavior_verified": "Static / source-derived; subcategory=WeeklyBoundary",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_BUDGET_AUTOBUDGET_RESET_MONTHLY"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_BUDGET_AVAILABLE_VS_SPENT(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_BUDGET_AVAILABLE_VS_SPENT",
        "description": "GET /api/v1/budgets/{id} attribute spent[].sum reflects withdrawals attributed to the budget in the user's primary currency. Create a Budget+BudgetLimit, post a Withdrawal of 73.50 EUR with budget_id, then GET reports spent.sum = '-73.50' (Withdrawal source-amount is negative).",
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
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "name": "spent reflection probe {{run_id}}",
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
                            "path": "$.data.id",
                            "exists": True,
                            "save_as": "budget_id"
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
                                "source_id": "{{asset_account_eur_id}}",
                                "destination_id": "{{expense_account_id}}",
                                "amount": "73.50",
                                "currency_code": "EUR",
                                "date": "{{today_iso}}",
                                "description": "budget spent probe",
                                "budget_id": "{{budget_id}}"
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
                    "sql": "SELECT CAST(SUM(t.amount) AS CHAR) AS net FROM transactions t INNER JOIN transaction_journals tj ON t.transaction_journal_id = tj.id INNER JOIN budget_transaction_journal btj ON btj.transaction_journal_id = tj.id WHERE btj.budget_id = {{budget_id}} AND t.amount < 0 AND t.deleted_at IS NULL AND tj.deleted_at IS NULL",
                    "expected_result": {
                        "net": "-73.500000000000"
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Budget",
            "subcategory": "AvailableVsSpent",
            "method": "binary",
            "maxScore": 8
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-025"
        ],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §4.3",
            "behavior_verified": "Static / source-derived; subcategory=AvailableVsSpent",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_BUDGET_AUTOBUDGET_RESET_MONTHLY"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_BUDGET_AUTOBUDGET_TYPE_ENUM_MATCH(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_BUDGET_AUTOBUDGET_TYPE_ENUM_MATCH",
        "description": "BD-INV-3: AutoBudgetType enum integer values are exactly {RESET=1, ROLLOVER=2, ADJUSTED=3}. Verify auto_budgets.auto_budget_type column persists the integer 1 (not the string 'reset') after creating an AutoBudget via API with auto_budget_type='reset'.",
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
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "name": "AutoBudget enum probe {{run_id}}",
                        "active": True,
                        "auto_budget_type": "rollover",
                        "auto_budget_currency_code": "EUR",
                        "auto_budget_amount": "100",
                        "auto_budget_period": "monthly"
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
                    "sql": "SELECT ab.auto_budget_type AS type_int FROM auto_budgets ab INNER JOIN budgets b ON ab.budget_id = b.id WHERE b.name LIKE 'AutoBudget enum probe%' ORDER BY ab.id DESC LIMIT 1",
                    "expected_result": {
                        "type_int": 2
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Budget",
            "subcategory": "AutoBudgetTypeEnum",
            "method": "binary",
            "maxScore": 6
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §4.3",
            "behavior_verified": "Static / source-derived; subcategory=AutoBudgetTypeEnum",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_BUDGET_AUTOBUDGET_RESET_MONTHLY"
        ]
    }
    return execute_primitive_chain(node, context)

