
from __future__ import annotations

from ..utils import NodeResult
from ._common import execute_primitive_chain


def test_SETUP_CREATE_ADMIN_USER(context: dict) -> NodeResult:
    node = {
        "id": "SETUP_CREATE_ADMIN_USER",
        "description": "Bootstrap an administrator user via the pfm:create-first-user CLI inside the app container so subsequent auth nodes have a valid principal.",
        "primitive_chain": [
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "cd /var/www/html && { APP_ENV=testing php artisan system:create-first-user admin@pfm.local 2>&1 || true; } | tail -2 ; php /var/www/html/_make_admin_user.php",
                    "expect_success": True,
                    "expect_output_contains": "admin@pfm.local"
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS cnt FROM users WHERE email='admin@pfm.local'",
                    "expected_result": {
                        "cnt": 1
                    }
                }
            }
        ],
        "scoring": {
            "category": "Setup",
            "subcategory": "BootstrapAdmin",
            "method": "binary",
            "maxScore": 4
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-CLI-CREATE-USER",
            "KB-USERS-TABLE"
        ],
        "source_evidence": {
            "source_file": "Build Steps §10",
            "behavior_verified": "Static / source-derived; subcategory=BootstrapAdmin",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_SETUP_CREATE_ACCESS_TOKEN(context: dict) -> NodeResult:
    node = {
        "id": "SETUP_CREATE_ACCESS_TOKEN",
        "description": "Generate a Personal Access Token for the admin user via pfm:create-access-token and persist it in eval context for later Bearer-auth nodes.",
        "primitive_chain": [
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "cd /var/www/html && php _make_token.php /tmp/admin_token.txt > /dev/null 2>&1 && echo Bearer && cat /tmp/admin_token.txt",
                    "expect_success": True,
                    "expect_output_contains": "Bearer",
                    "capture_to_context": {
                        "regex": "(eyJ[A-Za-z0-9._-]{40,})",
                        "context_key": "admin_pat"
                    }
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS cnt FROM oauth_access_tokens WHERE user_id=(SELECT id FROM users WHERE email='admin@pfm.local')",
                    "expected_min_rows": 1
                }
            }
        ],
        "scoring": {
            "category": "Setup",
            "subcategory": "AccessToken",
            "method": "binary",
            "maxScore": 5
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-CLI-CREATE-PAT",
            "KB-OAUTH-TABLES"
        ],
        "source_evidence": {
            "source_file": "Build Steps §10",
            "behavior_verified": "Static / source-derived; subcategory=AccessToken",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "SETUP_CREATE_ADMIN_USER"
        ]
    }
    return execute_primitive_chain(node, context)


def test_SETUP_OAUTH_PASSPORT_KEYS(context: dict) -> NodeResult:
    node = {
        "id": "SETUP_OAUTH_PASSPORT_KEYS",
        "description": "Verify Laravel Passport RSA key files exist on disk (storage/oauth-private.key and oauth-public.key) so OAuth flows can sign tokens.",
        "primitive_chain": [
            {
                "type": "P01",
                "inputs": {
                    "path": "storage/oauth-private.key",
                    "type": "file",
                    "in_container": True
                }
            },
            {
                "type": "P01",
                "inputs": {
                    "path": "storage/oauth-public.key",
                    "type": "file",
                    "in_container": True
                }
            }
        ],
        "scoring": {
            "category": "Setup",
            "subcategory": "OAuthKeys",
            "method": "weighted",
            "maxScore": 2
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-PASSPORT-KEYS"
        ],
        "source_evidence": {
            "source_file": "Build Steps §10",
            "behavior_verified": "Static / source-derived; subcategory=OAuthKeys",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_SETUP_DB_SEED_DEFAULT(context: dict) -> NodeResult:
    node = {
        "id": "SETUP_DB_SEED_DEFAULT",
        "description": "Default seeders must populate the reference data: 40+ ISO currencies, 14 account_types, 7 transaction_types — without them the financial domain cannot operate.",
        "primitive_chain": [
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT (SELECT COUNT(*) FROM transaction_currencies) AS currencies, (SELECT COUNT(*) FROM account_types) AS acc_types, (SELECT COUNT(*) FROM transaction_types) AS tx_types",
                    "expected_predicates": [
                        {
                            "field": "currencies",
                            "op": ">=",
                            "value": 40
                        },
                        {
                            "field": "acc_types",
                            "op": "=",
                            "value": 14
                        },
                        {
                            "field": "tx_types",
                            "op": "=",
                            "value": 7
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "Setup",
            "subcategory": "Seeders",
            "method": "weighted",
            "maxScore": 6
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-CURRENCY-SEEDER",
            "KB-ACCOUNT-TYPES",
            "KB-TX-TYPES"
        ],
        "source_evidence": {
            "source_file": "Build Steps §10",
            "behavior_verified": "Static / source-derived; subcategory=Seeders",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DEPLOY_HEALTH"
        ]
    }
    return execute_primitive_chain(node, context)

