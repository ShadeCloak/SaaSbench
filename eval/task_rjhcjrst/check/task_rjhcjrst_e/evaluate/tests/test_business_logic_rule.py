
from __future__ import annotations

from ..utils import NodeResult
from ._common import execute_primitive_chain


def test_BIZ_RULE_DESCRIPTION_CONTAINS_TRIGGER(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_RULE_DESCRIPTION_CONTAINS_TRIGGER",
        "description": "FP-RULE-ENGINE-SEARCH: Rule with trigger description_contains='cafe' + action add_tag='coffee'. Auto-fires after a journal create event (store-journal). Verify tag attached via tag_transaction_journal pivot. Tests that SearchRuleEngine uses gdbots search query, not Eloquent LIKE.",
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
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "title": "rule probe group {{run_id}}",
                        "active": True,
                        "order": 1
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
                            "save_as": "rg_id"
                        }
                    ]
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
                        "title": "description_contains cafe → add_tag coffee {{run_id}}",
                        "rule_group_id": "{{rg_id}}",
                        "active": True,
                        "strict": True,
                        "stop_processing": False,
                        "trigger": "store-journal",
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
                                "value": "coffee",
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
                                "amount": "4.50",
                                "currency_code": "EUR",
                                "date": "2026-04-15",
                                "description": "Cafe Lyon morning latte"
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
                    "sql": "SELECT COUNT(*) AS tagged FROM tag_transaction_journal ttj INNER JOIN transaction_journals tj ON ttj.transaction_journal_id = tj.id INNER JOIN tags t ON ttj.tag_id = t.id WHERE tj.description = 'Cafe Lyon morning latte' AND t.tag = 'coffee' AND tj.deleted_at IS NULL",
                    "expected_result": {
                        "tagged": 1
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Rule",
            "subcategory": "DescriptionContainsTrigger",
            "method": "binary",
            "maxScore": 12
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [
            "FP-RULE-ENGINE-SEARCH"
        ],
        "source_evidence": {
            "source_file": "Business Logic §5.1",
            "behavior_verified": "Static / source-derived; subcategory=DescriptionContainsTrigger",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_RULE_CREATE",
            "DB_TABLE_RULES"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_RULE_AMOUNT_MORE_TRIGGER(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_RULE_AMOUNT_MORE_TRIGGER",
        "description": "Rule with trigger amount_more='100' + action add_tag='big-purchase'. POST one transaction amount=150 (must trigger) and one amount=50 (must NOT trigger). P08 confirms only the 150 journal got tagged.",
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
                        "title": "amount_more 100 → add_tag big-purchase {{run_id}}",
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
                            }
                        ],
                        "actions": [
                            {
                                "type": "add_tag",
                                "value": "big-purchase",
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
                                "description": "amount_more positive probe"
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
                                "amount": "50.00",
                                "currency_code": "EUR",
                                "date": "2026-04-15",
                                "description": "amount_more negative probe"
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
                    "sql": "SELECT (SELECT COUNT(*) FROM tag_transaction_journal ttj INNER JOIN transaction_journals tj ON ttj.transaction_journal_id = tj.id INNER JOIN tags t ON ttj.tag_id = t.id WHERE tj.description = 'amount_more positive probe' AND t.tag = 'big-purchase') AS pos_tagged, (SELECT COUNT(*) FROM tag_transaction_journal ttj INNER JOIN transaction_journals tj ON ttj.transaction_journal_id = tj.id INNER JOIN tags t ON ttj.tag_id = t.id WHERE tj.description = 'amount_more negative probe' AND t.tag = 'big-purchase') AS neg_tagged",
                    "expected_result": {
                        "pos_tagged": 1,
                        "neg_tagged": 0
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Rule",
            "subcategory": "AmountMoreTrigger",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [
            "FP-RULE-ENGINE-SEARCH"
        ],
        "source_evidence": {
            "source_file": "Business Logic §5.1",
            "behavior_verified": "Static / source-derived; subcategory=AmountMoreTrigger",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_RULE_DESCRIPTION_CONTAINS_TRIGGER"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_RULE_STRICT_AND_VS_OR(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_RULE_STRICT_AND_VS_OR",
        "description": "Strict semantics (§5.1.10): Rule.strict=True → AND across triggers (all must match); Rule.strict=False → OR (any matches). Setup two rules with same triggers (amount_more=50 AND description_contains=alpha), differing only in strict flag. Probe a journal that satisfies trigger A but not B → only the OR rule fires.",
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
                        "title": "AND-strict probe rule {{run_id}}",
                        "rule_group_id": "{{rg_id}}",
                        "active": True,
                        "strict": True,
                        "stop_processing": False,
                        "trigger": "store-journal",
                        "triggers": [
                            {
                                "type": "amount_more",
                                "value": "50"
                            },
                            {
                                "type": "description_contains",
                                "value": "alpha"
                            }
                        ],
                        "actions": [
                            {
                                "type": "add_tag",
                                "value": "AND-tag",
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
                    "path": "/api/v1/rules",
                    "headers": {
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "title": "OR-nonstrict probe rule {{run_id}}",
                        "rule_group_id": "{{rg_id}}",
                        "active": True,
                        "strict": False,
                        "stop_processing": False,
                        "trigger": "store-journal",
                        "triggers": [
                            {
                                "type": "amount_more",
                                "value": "50"
                            },
                            {
                                "type": "description_contains",
                                "value": "alpha"
                            }
                        ],
                        "actions": [
                            {
                                "type": "add_tag",
                                "value": "OR-tag",
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
                                "amount": "75.00",
                                "currency_code": "EUR",
                                "date": "2026-04-15",
                                "description": "satisfies amount only not desc"
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
                    "sql": "SELECT (SELECT COUNT(*) FROM tag_transaction_journal ttj INNER JOIN transaction_journals tj ON ttj.transaction_journal_id = tj.id INNER JOIN tags t ON ttj.tag_id = t.id WHERE tj.description = 'satisfies amount only not desc' AND t.tag = 'AND-tag') AS and_tagged, (SELECT COUNT(*) FROM tag_transaction_journal ttj INNER JOIN transaction_journals tj ON ttj.transaction_journal_id = tj.id INNER JOIN tags t ON ttj.tag_id = t.id WHERE tj.description = 'satisfies amount only not desc' AND t.tag = 'OR-tag') AS or_tagged",
                    "expected_result": {
                        "and_tagged": 0,
                        "or_tagged": 1
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Rule",
            "subcategory": "StrictAndVsOr",
            "method": "binary",
            "maxScore": 12
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [
            "FP-RULE-ENGINE-SEARCH"
        ],
        "source_evidence": {
            "source_file": "Business Logic §5.1",
            "behavior_verified": "Static / source-derived; subcategory=StrictAndVsOr",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_RULE_DESCRIPTION_CONTAINS_TRIGGER"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_RULE_STOP_PROCESSING(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_RULE_STOP_PROCESSING",
        "description": "§5.1.10 Rule.stop_processing truth table: rule1 (stop_processing=True, action add_tag='first') fires successfully → rule2 (action add_tag='second', same group) MUST be skipped. Order rules by 'order' ASC.",
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
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "title": "stop-processing probe group {{run_id}}",
                        "active": True,
                        "order": 99
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
                            "save_as": "stop_rg_id"
                        }
                    ]
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
                        "title": "rule1 stop=True {{run_id}}",
                        "rule_group_id": "{{stop_rg_id}}",
                        "order": 1,
                        "active": True,
                        "strict": True,
                        "stop_processing": True,
                        "trigger": "store-journal",
                        "triggers": [
                            {
                                "type": "description_contains",
                                "value": "stop-probe"
                            }
                        ],
                        "actions": [
                            {
                                "type": "add_tag",
                                "value": "rule1-fired",
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
                    "path": "/api/v1/rules",
                    "headers": {
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "title": "rule2 stop=False {{run_id}}",
                        "rule_group_id": "{{stop_rg_id}}",
                        "order": 2,
                        "active": True,
                        "strict": True,
                        "stop_processing": False,
                        "trigger": "store-journal",
                        "triggers": [
                            {
                                "type": "description_contains",
                                "value": "stop-probe"
                            }
                        ],
                        "actions": [
                            {
                                "type": "add_tag",
                                "value": "rule2-fired",
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
                                "amount": "1.00",
                                "currency_code": "EUR",
                                "date": "2026-04-15",
                                "description": "stop-probe target"
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
                    "sql": "SELECT (SELECT COUNT(*) FROM tag_transaction_journal ttj INNER JOIN transaction_journals tj ON ttj.transaction_journal_id = tj.id INNER JOIN tags t ON ttj.tag_id = t.id WHERE tj.description = 'stop-probe target' AND t.tag = 'rule1-fired') AS r1, (SELECT COUNT(*) FROM tag_transaction_journal ttj INNER JOIN transaction_journals tj ON ttj.transaction_journal_id = tj.id INNER JOIN tags t ON ttj.tag_id = t.id WHERE tj.description = 'stop-probe target' AND t.tag = 'rule2-fired') AS r2",
                    "expected_result": {
                        "r1": 1,
                        "r2": 0
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Rule",
            "subcategory": "StopProcessing",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §5.1",
            "behavior_verified": "Static / source-derived; subcategory=StopProcessing",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_RULE_DESCRIPTION_CONTAINS_TRIGGER"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_RULE_ACTION_SET_CATEGORY(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_RULE_ACTION_SET_CATEGORY",
        "description": "§5.1.6 set_category action: find-or-create category by name and sync (replace existing). Verify after rule fires, transaction_journals.category_id (or categories pivot) resolves to the named category.",
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
                        "title": "set_category probe rule {{run_id}}",
                        "rule_group_id": "{{rg_id}}",
                        "active": True,
                        "strict": True,
                        "stop_processing": False,
                        "trigger": "store-journal",
                        "triggers": [
                            {
                                "type": "description_contains",
                                "value": "groceries-probe"
                            }
                        ],
                        "actions": [
                            {
                                "type": "set_category",
                                "value": "Groceries",
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
                                "amount": "23.45",
                                "currency_code": "EUR",
                                "date": "2026-04-15",
                                "description": "weekly groceries-probe shop"
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
                    "sql": "SELECT c.name AS cat_name FROM transaction_journals tj LEFT JOIN category_transaction_journal ctj ON ctj.transaction_journal_id = tj.id LEFT JOIN categories c ON c.id = ctj.category_id WHERE tj.description = 'weekly groceries-probe shop' AND tj.deleted_at IS NULL ORDER BY tj.id DESC LIMIT 1",
                    "expected_result": {
                        "cat_name": "Groceries"
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Rule",
            "subcategory": "ActionSetCategory",
            "method": "binary",
            "maxScore": 8
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §5.1",
            "behavior_verified": "Static / source-derived; subcategory=ActionSetCategory",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_RULE_DESCRIPTION_CONTAINS_TRIGGER"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_RULE_ACTION_SET_AMOUNT_BALANCED(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_RULE_ACTION_SET_AMOUNT_BALANCED",
        "description": "KB-035: set_amount action MUST update BOTH child Transaction rows of the journal (source negative, destination positive) so that SUM(amount)=0 invariant remains. Manually trigger rule on an existing journal, then assert the two rows are exactly ±new_amount.",
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
                                "amount": "10.00",
                                "currency_code": "EUR",
                                "date": "2026-04-15",
                                "description": "set_amount probe target"
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
                            "save_as": "tx_grp_id"
                        },
                        {
                            "path": "$.data.attributes.transactions[0].transaction_journal_id",
                            "exists": True,
                            "save_as": "tx_journal_id"
                        }
                    ]
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
                        "title": "set_amount probe rule {{run_id}}",
                        "rule_group_id": "{{rg_id}}",
                        "active": True,
                        "strict": True,
                        "stop_processing": False,
                        "trigger": "store-journal",
                        "triggers": [
                            {
                                "type": "description_contains",
                                "value": "set_amount probe target"
                            }
                        ],
                        "actions": [
                            {
                                "type": "set_amount",
                                "value": "42.00",
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
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.data.id",
                            "exists": True,
                            "save_as": "set_amount_rule_id"
                        }
                    ]
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/rules/{{set_amount_rule_id}}/trigger?journals[]={{tx_journal_id}}",
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
                    "sql": "SELECT CAST(MIN(t.amount) AS CHAR) AS neg, CAST(MAX(t.amount) AS CHAR) AS pos, CAST(SUM(t.amount) AS CHAR) AS net FROM transactions t WHERE t.transaction_journal_id = {{tx_journal_id}} AND t.deleted_at IS NULL",
                    "expected_result": {
                        "neg": "-42.000000000000",
                        "pos": "42.000000000000",
                        "net": "0.000000000000"
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Rule",
            "subcategory": "SetAmountBalanced",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-035"
        ],
        "_failure_point_refs": [
            "FP-DOUBLE-ENTRY-1"
        ],
        "source_evidence": {
            "source_file": "Business Logic §5.1",
            "behavior_verified": "Static / source-derived; subcategory=SetAmountBalanced",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_RULE_DESCRIPTION_CONTAINS_TRIGGER"
        ]
    }
    return execute_primitive_chain(node, context)

