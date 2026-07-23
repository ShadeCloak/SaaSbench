
from __future__ import annotations

from ..utils import NodeResult
from ._common import execute_primitive_chain


def test_BIZ_RECURRENCE_DAILY_FIRES(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_RECURRENCE_DAILY_FIRES",
        "description": "RC-INV-4: Daily Recurrence with first_date=yesterday + repetition=daily fires once on cron tick today. Verify exactly 1 journal created with journal_meta.name='recurrence_id' AND meta_value=recurrence.id.",
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
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "type": "withdrawal",
                        "title": "daily recurrence probe {{run_id}}",
                        "first_date": "{{yesterday_iso}}",
                        "active": True,
                        "apply_rules": False,
                        "nr_of_repetitions": 10,
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
                                "type": "withdrawal",
                                "amount": "5.00",
                                "currency_code": "EUR",
                                "description": "daily recurrence probe journal",
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
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.data.id",
                            "exists": True,
                            "save_as": "rec_id"
                        }
                    ]
                }
            },
            {
                "type": "P12",
                "inputs": {
                    "command": "php artisan firefly-iii:cron --create-recurring --force",
                    "container": "{{app_container}}",
                    "expect_success": True
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(DISTINCT tjm.transaction_journal_id) AS created_journals FROM journal_meta tjm WHERE tjm.name = 'recurrence_id' AND (tjm.data = '\"{{rec_id}}\"' OR tjm.data = '{{rec_id}}')",
                    "expected_min": {
                        "created_journals": 1
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Recurrence",
            "subcategory": "DailyFires",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §5.3",
            "behavior_verified": "Static / source-derived; subcategory=DailyFires",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_RECURRENCE_CREATE",
            "DB_TABLE_RECURRENCES"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_RECURRENCE_WEEKEND_TO_FRIDAY(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_RECURRENCE_WEEKEND_TO_FRIDAY",
        "description": "RC-INV-3 / KB-042: weekend=3 (WEEKEND_TO_FRIDAY) shifts a Saturday occurrence back to the prior Friday. Setup recurrence whose computed next fire date is a Saturday with weekend=3 → after cron, journal date = Friday.",
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
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "type": "withdrawal",
                        "title": "weekend-to-friday probe {{run_id}}",
                        "first_date": "{{weekend_recurrence_first_date}}",
                        "active": True,
                        "apply_rules": False,
                        "nr_of_repetitions": 12,
                        "repetitions": [
                            {
                                "type": "weekly",
                                "moment": "6",
                                "skip": 0,
                                "weekend": 3
                            }
                        ],
                        "transactions": [
                            {
                                "type": "withdrawal",
                                "amount": "1.00",
                                "currency_code": "EUR",
                                "description": "weekend-to-friday probe journal",
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
                "type": "P12",
                "inputs": {
                    "command": "php artisan firefly-iii:cron --create-recurring --force --date={{friday_before_recent_saturday}}",
                    "container": "{{app_container}}",
                    "expect_success": True
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT DAYOFWEEK(MAX(tj.date)) AS dow FROM transaction_journals tj WHERE tj.description = 'weekend-to-friday probe journal' AND tj.deleted_at IS NULL",
                    "expected_result": {
                        "dow": 6
                    },
                    "_note": "MySQL DAYOFWEEK: Friday=6, Saturday=7. The most-recent Saturday occurrence shifts back to the prior Friday (friday_before_recent_saturday), which the cron fires on that exact date."
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Recurrence",
            "subcategory": "WeekendToFriday",
            "method": "binary",
            "maxScore": 8
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-042"
        ],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §5.3",
            "behavior_verified": "Static / source-derived; subcategory=WeekendToFriday",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_RECURRENCE_DAILY_FIRES"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_RECURRENCE_NDOM_FIRST_MONDAY(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_RECURRENCE_NDOM_FIRST_MONDAY",
        "description": "RC-INV-2 / §5.3.9: ndom moment='1,1' = first Monday of month. Triggering firefly-iii:cron on or after first-Monday-of-month creates a journal whose tj.date equals that first Monday.",
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
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "type": "withdrawal",
                        "title": "ndom first-monday probe {{run_id}}",
                        "first_date": "{{first_day_of_current_month}}",
                        "active": True,
                        "apply_rules": False,
                        "nr_of_repetitions": 12,
                        "repetitions": [
                            {
                                "type": "ndom",
                                "moment": "1,1",
                                "skip": 0,
                                "weekend": 1
                            }
                        ],
                        "transactions": [
                            {
                                "type": "withdrawal",
                                "amount": "1500.00",
                                "currency_code": "EUR",
                                "description": "ndom first-monday rent",
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
                "type": "P12",
                "inputs": {
                    "command": "php artisan firefly-iii:cron --create-recurring --force --date={{first_monday_of_current_month}}",
                    "container": "{{app_container}}",
                    "expect_success": True
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT DATE_FORMAT(MAX(tj.date), '%Y-%m-%d') AS journal_date, DAYOFWEEK(MAX(tj.date)) AS dow FROM transaction_journals tj WHERE tj.description = 'ndom first-monday rent' AND tj.deleted_at IS NULL",
                    "expected_result": {
                        "journal_date": "{{first_monday_of_current_month}}",
                        "dow": 2
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Recurrence",
            "subcategory": "NdomFirstMonday",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §5.3",
            "behavior_verified": "Static / source-derived; subcategory=NdomFirstMonday",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_RECURRENCE_DAILY_FIRES"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_RECURRENCE_REPETITIONS_CAP(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_RECURRENCE_REPETITIONS_CAP",
        "description": "RC-INV-6 / KB-040: nr_of_repetitions=3 acts as USER-CONFIGURED CAP. Engine maintains running count = COUNT(transaction_journals tj JOIN journal_meta WHERE name='recurrence_id' AND data=rec.id). After cap reached, additional cron ticks MUST NOT create new journals.",
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
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "type": "withdrawal",
                        "title": "repetitions-cap probe {{run_id}}",
                        "first_date": "{{four_days_ago_iso}}",
                        "active": True,
                        "apply_rules": False,
                        "nr_of_repetitions": 3,
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
                                "type": "withdrawal",
                                "amount": "1.00",
                                "currency_code": "EUR",
                                "description": "cap probe journal",
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
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.data.id",
                            "exists": True,
                            "save_as": "cap_rec_id"
                        }
                    ]
                }
            },
            {
                "type": "P12",
                "inputs": {
                    "command": "php artisan firefly-iii:cron --create-recurring --force",
                    "container": "{{app_container}}",
                    "expect_success": True
                }
            },
            {
                "type": "P12",
                "inputs": {
                    "command": "php artisan firefly-iii:cron --create-recurring --force",
                    "container": "{{app_container}}",
                    "expect_success": True
                }
            },
            {
                "type": "P12",
                "inputs": {
                    "command": "php artisan firefly-iii:cron --create-recurring --force",
                    "container": "{{app_container}}",
                    "expect_success": True
                }
            },
            {
                "type": "P12",
                "inputs": {
                    "command": "php artisan firefly-iii:cron --create-recurring --force",
                    "container": "{{app_container}}",
                    "expect_success": True
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS journal_count FROM transaction_journals tj WHERE tj.description = 'cap probe journal' AND tj.deleted_at IS NULL",
                    "expected_result": {
                        "journal_count": 3
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Recurrence",
            "subcategory": "RepetitionsCap",
            "method": "binary",
            "maxScore": 12,
            "expected_reference_fail": "Reference limitation: nr_of_repetitions is not enforced as a hard cap on journal creation under forced catch-up cron. Empirically verified — a daily recurrence with nr_of_repetitions=3 and first_date 4 days ago, driven by repeated `firefly-iii:cron --create-recurring --force`, accrues 5 linked journals (scoped by journal_meta recurrence_id), exceeding 3. The repetitions count governs the computed repeat_until/occurrence generation window, not a running journal-count guard, so the 'additional ticks MUST NOT create journals' invariant is not observable via the forced-cron path."
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-040"
        ],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §5.3",
            "behavior_verified": "Static / source-derived; subcategory=RepetitionsCap",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_RECURRENCE_DAILY_FIRES"
        ]
    }
    return execute_primitive_chain(node, context)

