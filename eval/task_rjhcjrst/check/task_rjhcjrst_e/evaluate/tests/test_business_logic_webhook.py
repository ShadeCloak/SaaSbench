
from __future__ import annotations

from ..utils import NodeResult
from ._common import execute_primitive_chain


def test_BIZ_WEBHOOK_HMAC_SHA3_512(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_WEBHOOK_HMAC_SHA3_512",
        "description": "FP-WEBHOOK-SIGNATURE-ALG / KB-047: Signature header is HMAC over '{ts}.{payload}' using sha3-512 algorithm (NOT sha256). Register a webhook against a mock receiver, trigger STORE_TRANSACTION, then verify the receiver's recorded request includes the Signature header AND that hmac_sha3_512(secret, ts+'.'+payload) matches v1=<hex>.",
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
                            "title": "sha3-512 probe webhook {{run_id}}",
                            "url": "http://host.docker.internal:{{webhook_port}}/hook",
                            "secret": "test_secret_32_chars_xxxxxxxxxx12",
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
                                    "amount": "9.99",
                                    "currency_code": "EUR",
                                    "date": "2026-04-15",
                                    "description": "sha3-512 webhook probe"
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
                        "signature_verify": {
                            "algorithm": "sha3-512",
                            "secret": "test_secret_32_chars_xxxxxxxxxx12",
                            "preimage_template": "{ts}.{raw_payload}",
                            "header_pattern": "^t=(?P<ts>\\d+),v1=(?P<sig>[0-9a-f]{128})$"
                        }
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Webhook",
            "subcategory": "HMAC_SHA3_512",
            "method": "binary",
            "maxScore": 12,
            "expected_reference_fail": "Reference limitation: webhook signatures use HMAC-SHA256, not SHA3-512. Verified against a live delivery to the mock receiver — the Signature header is 't=<ts>,v1=<hex>' where v1 is 64 hex chars (256-bit SHA-256), e.g. v1=8884dd4b20bf4d2cc3132ebcc6ce86e06de4e9604e23e96c437c47f79d7d799e. A 128-hex (512-bit) SHA3-512 signature is never emitted, so the sha3-512 signature scheme this node asserts is not implemented."
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-047"
        ],
        "_failure_point_refs": [
            "FP-WEBHOOK-SIGNATURE-ALG"
        ],
        "source_evidence": {
            "source_file": "Business Logic §5.4",
            "behavior_verified": "Static / source-derived; subcategory=HMAC_SHA3_512",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_WEBHOOK_CREATE"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_WEBHOOK_TRIGGER_STORE_TRANSACTION(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_WEBHOOK_TRIGGER_STORE_TRANSACTION",
        "description": "WH-INV-1: WebhookTrigger.STORE_TRANSACTION (integer 100) fires on TransactionGroup creation. Register webhook with trigger=100, post a transaction, verify the mock receiver gets a POST AND webhook_messages.sent=True AND uuid present.",
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
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "title": "STORE_TRANSACTION probe webhook {{run_id}}",
                        "url": "http://host.docker.internal:{{webhook_port}}/hook-store",
                        "active": True,
                        "triggers": ["STORE_TRANSACTION"],
                        "responses": ["TRANSACTIONS"],
                        "deliveries": ["JSON"]
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
                            "save_as": "wh_id"
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
                                "amount": "11.11",
                                "currency_code": "EUR",
                                "date": "2026-04-15",
                                "description": "STORE_TRANSACTION probe"
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
                    "command": "php artisan firefly-iii:cron --send-webhook-messages --force && php artisan queue:work --once --stop-when-empty",
                    "container": "{{app_container}}",
                    "expect_success": True
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS sent_messages FROM webhook_messages wm WHERE wm.webhook_id = {{wh_id}} AND wm.sent = 1",
                    "expected_result": {
                        "sent_messages": 1
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Webhook",
            "subcategory": "TriggerStoreTransaction",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §5.4",
            "behavior_verified": "Static / source-derived; subcategory=TriggerStoreTransaction",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_WEBHOOK_CREATE"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_WEBHOOK_RETRY_3_TIMES(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_WEBHOOK_RETRY_3_TIMES",
        "description": "WH-INV-4 (max_attempts=3): Configure webhook to mock-receiver/always-500. After cron tick + queue worker drains all retries, expect EXACTLY 3 webhook_attempts rows for the message AND messages.errored=True.",
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
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "title": "retry probe webhook {{run_id}}",
                        "url": "http://host.docker.internal:{{webhook_port}}/always-500",
                        "active": True,
                        "triggers": ["STORE_TRANSACTION"],
                        "responses": ["TRANSACTIONS"],
                        "deliveries": ["JSON"]
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
                            "save_as": "retry_wh_id"
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
                                "amount": "1.23",
                                "currency_code": "EUR",
                                "date": "2026-04-15",
                                "description": "retry probe transaction"
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
                    "command": "for i in 1 2 3 4; do php artisan firefly-iii:cron --send-webhook-messages --force; php artisan queue:work --once --stop-when-empty; done",
                    "container": "{{app_container}}",
                    "expect_success": True
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS attempt_count, MAX(wm.errored) AS errored FROM webhook_attempts wa INNER JOIN webhook_messages wm ON wa.webhook_message_id = wm.id WHERE wm.webhook_id = {{retry_wh_id}}",
                    "expected_result": {
                        "attempt_count": 3,
                        "errored": 1
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Webhook",
            "subcategory": "Retry3Times",
            "method": "binary",
            "maxScore": 12
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §5.4",
            "behavior_verified": "Static / source-derived; subcategory=Retry3Times",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_WEBHOOK_CREATE"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_WEBHOOK_RESPONSE_TRANSACTIONS_PAYLOAD(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_WEBHOOK_RESPONSE_TRANSACTIONS_PAYLOAD",
        "description": "WH-INV-1 / §5.4.4: response=TRANSACTIONS (integer 200) → outbound payload.content contains TransactionGroup resource with attributes.transactions[*].amount. Mock receiver inspects body and verifies presence of $.content.attributes.transactions OR $.content.transactions key.",
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
                            "title": "response TRANSACTIONS probe {{run_id}}",
                            "url": "http://host.docker.internal:{{webhook_port}}/payload-shape",
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
                                    "amount": "7.77",
                                    "currency_code": "EUR",
                                    "date": "2026-04-15",
                                    "description": "TRANSACTIONS payload probe"
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
                        "body_contains": {
                            "trigger": "STORE_TRANSACTION",
                            "response": "TRANSACTIONS"
                        },
                        "body_jsonpath_exists": [
                            "$.uuid",
                            "$.content"
                        ]
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Webhook",
            "subcategory": "ResponseTransactionsPayload",
            "method": "binary",
            "maxScore": 8
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §5.4",
            "behavior_verified": "Static / source-derived; subcategory=ResponseTransactionsPayload",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_WEBHOOK_TRIGGER_STORE_TRANSACTION"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_WEBHOOK_DELIVERY_JSON_CONTENT_TYPE(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_WEBHOOK_DELIVERY_JSON_CONTENT_TYPE",
        "description": "WH-INV-1 / §5.4.5: delivery=JSON (integer 300) is the only implemented value; outbound HTTP request MUST set Content-Type: application/json. Mock receiver records all incoming headers; assert Content-Type == application/json AND User-Agent matches PFM/<version>.",
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
                            "title": "delivery JSON probe {{run_id}}",
                            "url": "http://host.docker.internal:{{webhook_port}}/headers",
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
                                    "amount": "0.50",
                                    "currency_code": "EUR",
                                    "date": "2026-04-15",
                                    "description": "JSON delivery probe"
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
                            "Content-Type": "^application/json",
                            "User-Agent": "^\\S+/\\S+"
                        }
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Webhook",
            "subcategory": "DeliveryJsonContentType",
            "method": "binary",
            "maxScore": 6
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §5.4",
            "behavior_verified": "Static / source-derived; subcategory=DeliveryJsonContentType",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_WEBHOOK_TRIGGER_STORE_TRANSACTION"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_WEBHOOK_INACTIVE_NOT_TRIGGERED(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_WEBHOOK_INACTIVE_NOT_TRIGGERED",
        "description": "WH-INV-10 / standard active-flag semantics: webhook with active=False MUST NOT enqueue a webhook_message when its trigger event fires. Negative case — verify webhook_messages count for the inactive webhook stays at 0 after a transaction create.",
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
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json"
                    },
                    "body": {
                        "title": "INACTIVE probe webhook {{run_id}}",
                        "url": "http://host.docker.internal:{{webhook_port}}/should-never-receive",
                        "active": False,
                        "triggers": ["STORE_TRANSACTION"],
                        "responses": ["TRANSACTIONS"],
                        "deliveries": ["JSON"]
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
                            "save_as": "inactive_wh_id"
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
                                "amount": "0.01",
                                "currency_code": "EUR",
                                "date": "2026-04-15",
                                "description": "inactive webhook probe"
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
                    "command": "php artisan firefly-iii:cron --send-webhook-messages --force && php artisan queue:work --once --stop-when-empty",
                    "container": "{{app_container}}"
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS msg_count FROM webhook_messages wm WHERE wm.webhook_id = {{inactive_wh_id}}",
                    "expected_result": {
                        "msg_count": 0
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_Webhook",
            "subcategory": "InactiveNotTriggered",
            "method": "binary",
            "maxScore": 6
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §5.4",
            "behavior_verified": "Static / source-derived; subcategory=InactiveNotTriggered",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "API_WEBHOOK_CREATE"
        ]
    }
    return execute_primitive_chain(node, context)

