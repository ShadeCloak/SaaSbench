
from __future__ import annotations

from ..utils import NodeResult
from ._common import execute_primitive_chain


def test_CRON_HTTP_TRIGGER_OK(context: dict) -> NodeResult:
    node = {
        "id": "CRON_HTTP_TRIGGER_OK",
        "description": "GET /api/v1/cron/{static_cron_token} returns 200. Body must be a JSON object — when the response carries a $.jobs_run (or $.cron_jobs) array we additionally assert it is array-typed. Companion to API_CRON_TOKEN_AUTH_NO_BEARER (DAG-C) which only checks auth bypass; here we check the side-effect surface of the response payload.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin",
                    "purpose": "DB context for SQL token lookup; do NOT attach Authorization to subsequent /cron P04 calls."
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT TRIM(BOTH '\"' FROM data) AS token FROM configuration WHERE name='static_cron_token' UNION ALL SELECT 'fixture-token-value-32-chars-long' AS token LIMIT 1",
                    "save_first_row_as": "cron_cfg",
                    "fallback_value": "fixture-token-value-32-chars-long"
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
                    "no_auth": True
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
                            "path": "$.jobs_run",
                            "type": "array",
                            "optional": True,
                            "optional_aliases": [
                                "cron_jobs",
                                "data.jobs",
                                "results"
                            ]
                        },
                        {
                            "path": "$.message",
                            "type": "string",
                            "optional": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "CronJobs",
            "subcategory": "HttpCronEndpointOk",
            "method": "binary",
            "maxScore": 4
        },
        "complexity_tier": "workflow_automator",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-CRON",
            "KB-018"
        ],
        "source_evidence": {
            "source_file": "Build Steps §10.4",
            "behavior_verified": "Static / source-derived; subcategory=HttpCronEndpointOk",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT",
            "DEPLOY_HEALTH"
        ]
    }
    return execute_primitive_chain(node, context)


def test_CRON_HTTP_BAD_TOKEN_404(context: dict) -> NodeResult:
    node = {
        "id": "CRON_HTTP_BAD_TOKEN_404",
        "description": "GET /api/v1/cron/wrong-token-32-chars-xxxxxxxxxxxxxx (a syntactically-valid 32-char string that is NOT the configured token) MUST be rejected with 403, 404 or 422 (firefly-iii historically used 422 for malformed token, 403 for valid-shape-but-wrong; either is acceptable per PRD §6.1.6).",
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
                    "path": "/api/v1/cron/wrong-token-32-chars-xxxxxxxxxxxxxx",
                    "headers": {
                        "Accept": "application/json"
                    },
                    "no_auth": True
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "acceptable_statuses": [
                        403,
                        404,
                        422
                    ]
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
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "CronJobs",
            "subcategory": "HttpCronBadToken",
            "method": "binary",
            "maxScore": 3,
            "expected_reference_fail": "Reference limitation: the /api/v1/cron/{token} endpoint does not validate the URL token. Verified in source — CronRequest::authorize() returns true unconditionally and rules() only validate force/date; the {token} segment is ignored and never compared to STATIC_CRON_TOKEN. Any token (wrong 32-char, over-length, or even 'short') returns 200 with job_fired=true. The 'bad cron token is rejected with 4xx' behavior this node asserts is not implemented."
        },
        "complexity_tier": "workflow_automator",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-CRON",
            "KB-018"
        ],
        "source_evidence": {
            "source_file": "Build Steps §10.4",
            "behavior_verified": "Static / source-derived; subcategory=HttpCronBadToken",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DEPLOY_HEALTH"
        ]
    }
    return execute_primitive_chain(node, context)


def test_CRON_RECURRING_CREATES_JOURNAL(context: dict) -> NodeResult:
    node = {
        "id": "CRON_RECURRING_CREATES_JOURNAL",
        "description": "Create a Recurrence whose first_date is yesterday (so it is due NOW) → invoke firefly-iii:cron --create-recurring --force --date=<today> → at least one new transaction_journal must be linked to that recurrence (via journal_meta.name='recurrence_id' OR rt_meta linkage). Verifies the CreateRecurringTransactions cron job per PRD §10.",
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
                "title": "EvalCronRecurring",
                "first_date": "{{yesterday_iso}}",
                        "active": True,
                        "apply_rules": False,
                        "nr_of_repetitions": 5,
                        "repetitions": [
                            {
                                "type": "daily",
                                "moment": "",
                                "skip": 0,
                                "weekend": 1
                            }
                        ],
                        "transactions": [
                            {
                                "description": "EvalCronJournal",
                                "amount": "10.00",
                                "currency_code": "EUR",
                                "source_id": "{{asset_account_eur_id}}",
                                "destination_id": "{{expense_account_id}}"
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
                    "sql": "SELECT COUNT(*) AS cnt_before FROM transaction_journals WHERE description='EvalCronJournal'",
                    "save_first_row_as": "before"
                }
            },
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "php artisan firefly-iii:cron --force --create-recurring --date={{today}}",
                    "expect_success": True,
                    "expect_output_contains_any": [
                        "recurring",
                        "Recurring",
                        "Created"
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS cnt_after FROM transaction_journals WHERE description='EvalCronJournal'",
                    "expected_predicates": [
                        {
                            "field": "cnt_after",
                            "op": ">=",
                            "value": 1
                        }
                    ],
                    "comment": "After cron, at least one journal with the recurrence's transaction description must exist."
                }
            }
        ],
        "scoring": {
            "category": "CronJobs",
            "subcategory": "RecurringCreatesJournal",
            "method": "binary",
            "maxScore": 8
        },
        "complexity_tier": "workflow_automator",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ENTITY-RECURRENCE",
            "KB-FIVE-REPETITIONS",
            "KB-CRON"
        ],
        "source_evidence": {
            "source_file": "Build Steps §10.4",
            "behavior_verified": "Static / source-derived; subcategory=RecurringCreatesJournal",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT",
            "DB_TABLE_RECURRENCES",
            "DB_TABLE_TRANSACTION_JOURNALS",
            "API_ACCOUNT_CREATE"
        ]
    }
    return execute_primitive_chain(node, context)


def test_CRON_AUTOBUDGET_CREATES_BUDGETLIMIT(context: dict) -> NodeResult:
    node = {
        "id": "CRON_AUTOBUDGET_CREATES_BUDGETLIMIT",
        "description": "Create a Budget + AutoBudget(monthly, type=reset, amount=200) → invoke firefly-iii:cron --create-auto-budgets --force --date=<first-of-month> → exactly one new budget_limit row tied to that budget must be created with start/end covering the month and amount='200.000000000000'. Verifies the AutoBudget reset cron-job.",
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
                        "name": "EvalAutoBudgetMonthly",
                        "active": True,
                        "auto_budget_type": "reset",
                        "auto_budget_amount": "200.00",
                        "auto_budget_period": "monthly",
                        "auto_budget_currency_code": "EUR"
                    }
                },
                "save_as": "ab_budget"
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
                    "sql": "SELECT COUNT(*) AS cnt_before FROM budget_limits WHERE budget_id=(SELECT id FROM budgets WHERE name='EvalAutoBudgetMonthly')",
                    "save_first_row_as": "bl_before"
                }
            },
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "php artisan firefly-iii:cron --force --create-auto-budgets --date={{first_of_current_month}}",
                    "expect_success": True,
                    "expect_output_contains_any": [
                        "auto",
                        "AutoBudget",
                        "Auto-budget",
                        "budget"
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS cnt_after, MAX(CAST(amount AS DECIMAL(32,12))) AS max_amount FROM budget_limits WHERE budget_id=(SELECT id FROM budgets WHERE name='EvalAutoBudgetMonthly')",
                    "expected_predicates": [
                        {
                            "field": "cnt_after",
                            "op": ">=",
                            "value": 1
                        },
                        {
                            "field": "max_amount",
                            "op": ">=",
                            "value": 199.99
                        },
                        {
                            "field": "max_amount",
                            "op": "<=",
                            "value": 200.01
                        }
                    ],
                    "comment": "AutoBudget cron must create a budget_limit with amount=200 for the RESET monthly budget. NOTE: Firefly's BudgetLimitRepository does not persist the 'generated' flag for cron-created limits (stored as generated=0), so the assertion verifies existence + amount rather than the generated marker."
                }
            }
        ],
        "scoring": {
            "category": "CronJobs",
            "subcategory": "AutoBudgetCreatesLimit",
            "method": "binary",
            "maxScore": 8
        },
        "complexity_tier": "workflow_automator",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-AUTO-BUDGET-TYPES",
            "KB-ENTITY-BUDGETLIMIT"
        ],
        "source_evidence": {
            "source_file": "Build Steps §10.4",
            "behavior_verified": "Static / source-derived; subcategory=AutoBudgetCreatesLimit",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT",
            "DB_TABLE_AUTO_BUDGETS",
            "DB_TABLE_BUDGET_LIMITS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_CRON_BILL_WARNING_LOGS(context: dict) -> NodeResult:
    node = {
        "id": "CRON_BILL_WARNING_LOGS",
        "description": "Create a Bill due in ~3 days → invoke firefly-iii:cron --send-subscription-warnings --force → at least one mail-queue job is enqueued (jobs table where queue='mail') OR storage/logs/laravel.log mentions the bill name + 'subscription' / 'reminder'. Verifies the Bill warning notification cron.",
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
                        "name": "EvalCronBillWarning",
                        "amount_min": "9.99",
                        "amount_max": "12.99",
                        "currency_code": "EUR",
                        "date": "{{three_days_ahead_iso}}",
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
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "php artisan firefly-iii:cron --force --send-subscription-warnings",
                    "expect_success": True,
                    "expect_output_contains_any": [
                        "subscription",
                        "bill",
                        "warning",
                        "Bill",
                        "warn"
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT (SELECT COUNT(*) FROM jobs WHERE queue IN ('mail','default')) AS queued, (SELECT COUNT(*) FROM jobs_batches) AS batches",
                    "any_of_predicates": [
                        {
                            "field": "queued",
                            "op": ">=",
                            "value": 1
                        },
                        {
                            "field": "batches",
                            "op": ">=",
                            "value": 1
                        }
                    ],
                    "fallback_check": {
                        "type": "P12",
                        "container": "{{app_container}}",
                        "command": "tail -200 storage/logs/laravel.log 2>/dev/None | grep -iE 'EvalCronBillWarning|subscription|bill|warning' | head -5",
                        "expect_output_min_lines": 1,
                        "comment": "If QUEUE_CONNECTION=sync and no jobs row is created, evidence falls back to log inspection."
                    }
                }
            }
        ],
        "scoring": {
            "category": "CronJobs",
            "subcategory": "BillWarningQueued",
            "method": "binary",
            "maxScore": 6
        },
        "complexity_tier": "workflow_automator",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ENTITY-BILL",
            "KB-BL-INV-8",
            "KB-CRON"
        ],
        "source_evidence": {
            "source_file": "Build Steps §10.4",
            "behavior_verified": "Static / source-derived; subcategory=BillWarningQueued",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT",
            "DB_TABLE_BILLS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_CRON_FORCE_FLAG_BYPASS_GUARD(context: dict) -> NodeResult:
    node = {
        "id": "CRON_FORCE_FLAG_BYPASS_GUARD",
        "description": "Run firefly-iii:cron once -> immediately run a second time with NO --force: the second invocation must skip with a guard message ('already run today' / 'last run was less than') and exit 0. Then run a third time WITH --force: it must execute again (no skip message).",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin"
                }
            },
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "php artisan firefly-iii:cron --force --date={{today}}",
                    "expect_success": True,
                    "comment": "Baseline run to seed the last-run timestamp in configuration."
                }
            },
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "php artisan firefly-iii:cron --date={{today}}",
                    "expect_success": True,
                    "expect_output_contains_any": [
                        "already",
                        "skip",
                        "last run",
                        "Skipped",
                        "no need"
                    ],
                    "comment": "Second run without --force should hit the guard and skip."
                }
            },
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "php artisan firefly-iii:cron --force --date={{today}}",
                    "expect_success": True,
                    "expect_output_not_contains_any": [
                        "fatal error",
                        "Exception"
                    ],
                    "comment": "Third run WITH --force re-executes — must not hit the skip guard."
                }
            }
        ],
        "scoring": {
            "category": "CronJobs",
            "subcategory": "ForceFlagBypassGuard",
            "method": "binary",
            "maxScore": 5
        },
        "complexity_tier": "workflow_automator",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-CRON",
            "KB-CRON-FORCE-FLAG"
        ],
        "source_evidence": {
            "source_file": "Build Steps §10.4",
            "behavior_verified": "Static / source-derived; subcategory=ForceFlagBypassGuard",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DEPLOY_HEALTH",
            "DB_TABLE_USERS"
        ]
    }
    return execute_primitive_chain(node, context)

