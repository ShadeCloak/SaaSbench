
from __future__ import annotations

from ..utils import NodeResult
from ._common import execute_primitive_chain


def test_BIZ_PIGGY_ADD_EVENT_UPDATES_CURRENT(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_PIGGY_ADD_EVENT_UPDATES_CURRENT",
        "description": "PB-INV-3,4: POST /api/v1/piggy-banks/{id}/events {amount:'100'} → account_piggy_bank pivot.current_amount becomes 100, AND a piggy_bank_events row with positive amount=100 is inserted.",
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
                    "path": "/api/v1/piggy-banks",
                    "headers": {
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "name": "Vacation 2026 {{run_id}}",
                        "target_amount": "1000.00",
                        "currency_code": "EUR",
                        "start_date": "{{first_of_current_month}}",
                        "transaction_currency_id": "{{eur_currency_id}}",
                        "active": True,
                        "order": 1,
                        "accounts": [
                            {
                                "account_id": "{{asset_account_eur_id}}",
                                "current_amount": "0.00"
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
                            "save_as": "piggy_id"
                        }
                    ]
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "PUT",
                    "path": "/api/v1/piggy-banks/{{piggy_id}}",
                    "headers": {
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "accounts": [
                            {
                                "account_id": "{{asset_account_eur_id}}",
                                "current_amount": "100"
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
                    "sql": "SELECT CAST(MAX(apb.current_amount) AS CHAR) AS pivot_amt, (SELECT COUNT(*) FROM piggy_bank_events pe WHERE pe.piggy_bank_id = {{piggy_id}} AND pe.amount > 0) AS event_count FROM account_piggy_bank apb WHERE apb.piggy_bank_id = {{piggy_id}}",
                    "expected_result": {
                        "pivot_amt": "100.000000000000",
                        "event_count": 1
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_PiggyBank",
            "subcategory": "AddEventUpdatesCurrent",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [
            "FP-PIVOT-TABLE-NAMING"
        ],
        "source_evidence": {
            "source_file": "Business Logic §5.2",
            "behavior_verified": "Static / source-derived; subcategory=AddEventUpdatesCurrent",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "DB_TABLE_PIGGY_BANKS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_PIGGY_REMOVE_EVENT_DECREMENTS(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_PIGGY_REMOVE_EVENT_DECREMENTS",
        "description": "PB-INV-5: removeAmount uses bcsub. After add(100) then remove(30), pivot.current_amount = 70 and a NEGATIVE-amount event row exists.",
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
                    "path": "/api/v1/piggy-banks/{{piggy_id}}",
                    "headers": {
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "accounts": [
                            {
                                "account_id": "{{asset_account_eur_id}}",
                                "current_amount": "70"
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
                    "sql": "SELECT CAST(MAX(apb.current_amount) AS CHAR) AS pivot_amt, (SELECT COUNT(*) FROM piggy_bank_events pe WHERE pe.piggy_bank_id = {{piggy_id}} AND pe.amount < 0) AS neg_events FROM account_piggy_bank apb WHERE apb.piggy_bank_id = {{piggy_id}}",
                    "expected_result": {
                        "pivot_amt": "70.000000000000",
                        "neg_events": 1
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_PiggyBank",
            "subcategory": "RemoveEventDecrements",
            "method": "binary",
            "maxScore": 8
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §5.2",
            "behavior_verified": "Static / source-derived; subcategory=RemoveEventDecrements",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_PIGGY_ADD_EVENT_UPDATES_CURRENT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_PIGGY_RULE_ACTION_UPDATE(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_PIGGY_RULE_ACTION_UPDATE",
        "description": "§5.2.5 update_piggy rule action with idempotent dedup via piggy_bank_events.transaction_journal_id. Setup rule: trigger description_contains='savings' + action update_piggy=<piggy_id>. Post a Withdrawal that sources from the asset account linked to the piggy → pivot.current_amount decrements by transaction amount.",
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
                    "path": "/api/v1/piggy-banks",
                    "headers": {
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "no_auto_capture": True,
                    "capture_to_context": {
                        "context_key": "rule_action_piggy_id",
                        "json_path": "$.data.id"
                    },
                    "body": {
                        "name": "RuleActionPiggy {{run_id}}",
                        "target_amount": "1000.00",
                        "currency_code": "EUR",
                        "start_date": "{{first_of_current_month}}",
                        "transaction_currency_id": "{{eur_currency_id}}",
                        "active": True,
                        "accounts": [
                            {
                                "account_id": "{{asset_account_eur_id}}",
                                "current_amount": "100.00"
                            }
                        ]
                    },
                    "comment": "Create the piggy INSIDE this node (linked to the very account the withdrawal below sources from). update_piggy only records a piggy_bank_event when the transaction touches the piggy's linked account; creating it here keeps the link and the withdrawal source consistent within one atomic chain, immune to shared-context asset_account_eur_id churn from unrelated nodes."
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
                        "title": "update_piggy probe rule {{run_id}}",
                        "rule_group_id": "{{rg_id}}",
                        "active": True,
                        "strict": True,
                        "stop_processing": False,
                        "trigger": "store-journal",
                        "triggers": [
                            {
                                "type": "description_contains",
                                "value": "savings-probe"
                            }
                        ],
                        "actions": [
                            {
                                "type": "update_piggy",
                                "value": "RuleActionPiggy {{run_id}}",
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
                                "amount": "10.00",
                                "currency_code": "EUR",
                                "date": "2026-04-15",
                                "description": "savings-probe transfer"
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
                    "sql": "SELECT COUNT(*) AS event_linked FROM piggy_bank_events pe WHERE pe.piggy_bank_id = {{rule_action_piggy_id}} AND pe.transaction_journal_id IS NOT NULL",
                    "expected_result": {
                        "event_linked": 1
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_PiggyBank",
            "subcategory": "RuleActionUpdate",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §5.2",
            "behavior_verified": "Static / source-derived; subcategory=RuleActionUpdate",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_PIGGY_ADD_EVENT_UPDATES_CURRENT",
            "BIZ_RULE_DESCRIPTION_CONTAINS_TRIGGER"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_PIGGY_TARGET_REACHED_FLAG(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_PIGGY_TARGET_REACHED_FLAG",
        "description": "PB-INV-6: When current_amount reaches target_amount, response should expose a 'percentage' (or saved-fraction) of 1.0/100. Verify GET /api/v1/piggy-banks/{id} attribute reflects 100% saved.",
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
                    "path": "/api/v1/piggy-banks",
                    "headers": {
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "name": "TargetReached probe {{run_id}}",
                        "target_amount": "100.00",
                        "currency_code": "EUR",
                        "start_date": "{{first_of_current_month}}",
                        "transaction_currency_id": "{{eur_currency_id}}",
                        "active": True,
                        "order": 2,
                        "accounts": [
                            {
                                "account_id": "{{asset_account_eur_id}}",
                                "current_amount": "100.00"
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
                            "save_as": "tgt_piggy_id"
                        }
                    ]
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/piggy-banks/{{tgt_piggy_id}}",
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
                            "path": "$.data.attributes.target_amount",
                            "expected": "100",
                            "match": "starts_with"
                        },
                        {
                            "path": "$.data.attributes.current_amount",
                            "expected": "100",
                            "match": "starts_with"
                        },
                        {
                            "path": "$.data.attributes.percentage",
                            "expected": 100,
                            "tolerance": 1
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_PiggyBank",
            "subcategory": "TargetReachedFlag",
            "method": "binary",
            "maxScore": 6
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §5.2",
            "behavior_verified": "Static / source-derived; subcategory=TargetReachedFlag",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_PIGGY_ADD_EVENT_UPDATES_CURRENT"
        ]
    }
    return execute_primitive_chain(node, context)

