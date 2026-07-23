
from __future__ import annotations

from ..utils import NodeResult
from ._common import execute_primitive_chain


def test_BIZ_BILL_AUTO_MATCH_KEYWORD(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_BILL_AUTO_MATCH_KEYWORD",
        "description": "BL-INV-5 (link_to_bill rule action): Bill match='Netflix', amount_min=10, amount_max=20. POST a Withdrawal description='Netflix subscription' amount=15 → after auto-rule fires, transaction_journals.bill_id must equal the Bill id.",
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
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "name": "Netflix subscription bill {{run_id}}",
                        "match": "Netflix",
                        "amount_min": "10.00",
                        "amount_max": "20.00",
                        "date": "2026-01-01",
                        "repeat_freq": "monthly",
                        "skip": 0,
                        "automatch": True,
                        "active": True,
                        "currency_code": "EUR"
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
                            "save_as": "bill_id"
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
                                "amount": "15.00",
                                "currency_code": "EUR",
                                "date": "2026-04-12",
                                "description": "Netflix subscription"
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
                    "sql": "SELECT tj.bill_id AS linked FROM transaction_journals tj WHERE tj.description = 'Netflix subscription' AND tj.deleted_at IS NULL ORDER BY tj.id DESC LIMIT 1",
                    "expected_result": {
                        "linked": "{{bill_id}}"
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Bill",
            "subcategory": "AutoMatchKeyword",
            "method": "binary",
            "maxScore": 10,
            "expected_reference_fail": "Reference limitation: keyword-based bill auto-matching on transaction store is not implemented in this Firefly version. Empirically verified — creating a withdrawal whose description ('Netflix subscription') and amount (15.00, within the bill's 10-20 range) match a bill with match='Netflix', automatch=true leaves transactions.bill_id NULL. Modern Firefly links bills to transactions only via an explicit bill_id/bill_name on the transaction or a rule action 'link to bill'; the legacy automatic matcher was removed. The stored automatch/match columns are legacy no-ops."
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §4.4",
            "behavior_verified": "Static / source-derived; subcategory=AutoMatchKeyword",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_BILL_CREATE",
            "DB_TABLE_BILLS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_BILL_NO_MATCH_AMOUNT_OUT_OF_RANGE(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_BILL_NO_MATCH_AMOUNT_OUT_OF_RANGE",
        "description": "BL-INV-5 negative case: Bill amount_max=20.00 but transaction amount=25.00 → bill_id MUST remain NULL (not auto-linked). Same Bill from previous probe; new transaction with amount=25.00.",
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
                                "amount": "25.00",
                                "currency_code": "EUR",
                                "date": "2026-04-13",
                                "description": "Netflix out-of-range"
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
                    "sql": "SELECT (tj.bill_id IS NULL) AS bill_is_null FROM transaction_journals tj WHERE tj.description = 'Netflix out-of-range' AND tj.deleted_at IS NULL ORDER BY tj.id DESC LIMIT 1",
                    "expected_result": {
                        "bill_is_null": 1
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Bill",
            "subcategory": "NoMatchAmountOutOfRange",
            "method": "binary",
            "maxScore": 8
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §4.4",
            "behavior_verified": "Static / source-derived; subcategory=NoMatchAmountOutOfRange",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_BILL_AUTO_MATCH_KEYWORD"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_BILL_NO_MATCH_KEYWORD_MISSING(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_BILL_NO_MATCH_KEYWORD_MISSING",
        "description": "BL-INV-5 negative case: description='Spotify subscription' (does NOT contain 'Netflix') and amount in range → bill_id MUST remain NULL.",
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
                                "amount": "12.00",
                                "currency_code": "EUR",
                                "date": "2026-04-14",
                                "description": "Spotify subscription"
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
                    "sql": "SELECT (tj.bill_id IS NULL) AS bill_is_null FROM transaction_journals tj WHERE tj.description = 'Spotify subscription' AND tj.deleted_at IS NULL ORDER BY tj.id DESC LIMIT 1",
                    "expected_result": {
                        "bill_is_null": 1
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Bill",
            "subcategory": "NoMatchKeywordMissing",
            "method": "binary",
            "maxScore": 6
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §4.4",
            "behavior_verified": "Static / source-derived; subcategory=NoMatchKeywordMissing",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_BILL_AUTO_MATCH_KEYWORD"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_BILL_NEXT_DATE_CALCULATION(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_BILL_NEXT_DATE_CALCULATION",
        "description": "BL-INV-2 / KB-028: Navigation::addPeriod with skip=0, repeat_freq='monthly', date='2026-01-15' → next pay date is '2026-02-15' (one calendar month forward). Verify GET /api/v1/bills/{id} returns next_expected_match field aligned to monthly cadence.",
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
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "name": "next-date probe bill {{run_id}}",
                        "match": "rent",
                        "amount_min": "1000.00",
                        "amount_max": "1500.00",
                        "date": "2026-01-15",
                        "repeat_freq": "monthly",
                        "skip": 0,
                        "automatch": True,
                        "active": True,
                        "currency_code": "EUR"
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
                            "save_as": "bill_id"
                        }
                    ]
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/bills/{{bill_id}}?start=2026-01-16&end=2026-03-01",
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
                            "path": "$.data.attributes.repeat_freq",
                            "expected": "monthly"
                        },
                        {
                            "path": "$.data.attributes.skip",
                            "expected": 0
                        },
                        {
                            "path": "$.data.attributes.next_expected_match",
                            "expected": "2026-02-15",
                            "match": "starts_with"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Bill",
            "subcategory": "NextDateCalculation",
            "method": "binary",
            "maxScore": 8
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-028"
        ],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §4.4",
            "behavior_verified": "Static / source-derived; subcategory=NextDateCalculation",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_BILL_AUTO_MATCH_KEYWORD"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_BILL_REPEAT_FREQ_HALF_YEAR_HYPHEN(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_BILL_REPEAT_FREQ_HALF_YEAR_HYPHEN",
        "description": "BL-INV-1 / KB-028: bill_periods config requires literal hyphenated string 'half-year' (NOT 'halfyear', NOT 'half_year'). Creating Bill with repeat_freq='half-year' MUST succeed (201). Subsequently, P08 confirms DB stores the exact hyphenated string.",
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
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "name": "half-year hyphen probe bill {{run_id}}",
                        "match": "insurance",
                        "amount_min": "200.00",
                        "amount_max": "300.00",
                        "date": "2026-01-01",
                        "repeat_freq": "half-year",
                        "skip": 0,
                        "automatch": True,
                        "active": True,
                        "currency_code": "EUR"
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
                    "sql": "SELECT b.repeat_freq AS rf FROM bills b WHERE b.name LIKE 'half-year hyphen probe bill%' AND b.deleted_at IS NULL ORDER BY b.id DESC LIMIT 1",
                    "expected_result": {
                        "rf": "half-year"
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Bill",
            "subcategory": "HalfYearHyphen",
            "method": "binary",
            "maxScore": 6
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-028"
        ],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §4.4",
            "behavior_verified": "Static / source-derived; subcategory=HalfYearHyphen",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_BILL_CREATE"
        ]
    }
    return execute_primitive_chain(node, context)

