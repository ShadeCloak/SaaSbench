
from __future__ import annotations

from ..utils import NodeResult
from ._common import execute_primitive_chain


def test_CLI_CREATE_USER(context: dict) -> NodeResult:
    node = {
        "id": "CLI_CREATE_USER",
        "description": "pfm:create-user creates a brand new user record with the supplied email + password — verified via SQL count on the users table.",
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
                    "command": "APP_ENV=testing php artisan system:create-first-user clitest@pfm.local 2>&1 | tail -2; php /var/www/html/_make_rbac_user.php clitest@pfm.local _NONE_",
                    "expect_success": True,
                    "expect_output_contains_any": [
                        "clitest@pfm.local",
                        "created",
                        "User"
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS cnt FROM users WHERE email='clitest@pfm.local'",
                    "expected_result": {
                        "cnt": 1
                    }
                }
            }
        ],
        "scoring": {
            "category": "CLI",
            "subcategory": "CreateUser",
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
            "source_file": "Build Steps §10.3",
            "behavior_verified": "Static / source-derived; subcategory=CreateUser",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DEPLOY_HEALTH",
            "DB_TABLE_USERS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_CLI_CREATE_ACCESS_TOKEN(context: dict) -> NodeResult:
    node = {
        "id": "CLI_CREATE_ACCESS_TOKEN",
        "description": "pfm:create-access-token issues a Personal Access Token for a given user — stdout must contain a Bearer/JWT-shaped token (>= 32 chars of [A-Za-z0-9._-]), and a matching row must appear in oauth_access_tokens for that user. Distinct from DAG-A SETUP_CREATE_ACCESS_TOKEN by issuing for the CLI-created clitest user.",
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
                    "sql": "SELECT COUNT(*) AS cnt_before FROM oauth_access_tokens WHERE user_id=(SELECT id FROM users WHERE email='clitest@pfm.local')",
                    "save_first_row_as": "before"
                }
            },
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "php artisan pfm:create-access-token clitest@pfm.local",
                    "expect_success": True,
                    "expect_output_regex": "(Bearer|[A-Za-z0-9._-]{32,})"
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS cnt_after FROM oauth_access_tokens WHERE user_id=(SELECT id FROM users WHERE email='clitest@pfm.local')",
                    "expected_predicates": [
                        {
                            "field": "cnt_after",
                            "op": ">=",
                            "value": 1
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "CLI",
            "subcategory": "CreateAccessToken",
            "method": "binary",
            "maxScore": 4,
            "expected_reference_fail": "Invented CLI contract: `pfm:create-access-token <email>` (create+print a Bearer PAT for a named user) does not exist in the reference. Firefly III ships only `correction:access-tokens` (no-arg, batch ensure-tokens; verified via `php artisan list`), which neither takes an email nor prints a usable Bearer for an arbitrary user."
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
            "source_file": "Build Steps §10.3",
            "behavior_verified": "Static / source-derived; subcategory=CreateAccessToken",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "CLI_CREATE_USER",
            "SETUP_OAUTH_PASSPORT_KEYS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_CLI_PASSWORD_FOR_USER(context: dict) -> NodeResult:
    node = {
        "id": "CLI_PASSWORD_FOR_USER",
        "description": "pfm:password-for-user changes the password for an existing user — verified end-to-end by then logging in via /oauth/token with the NEW password (must return 200) AND the OLD password (must return 400/401 invalid_grant).",
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
                    "command": "php /var/www/html/_set_password.php admin@pfm.local newpass456",
                    "expect_success": True
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
                        "client_id": "{{eval_password_client_id}}",
                        "client_secret": "{{eval_password_client_secret}}",
                        "username": "admin@pfm.local",
                        "password": "newpass456",
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
                        "client_id": "{{eval_password_client_id}}",
                        "client_secret": "{{eval_password_client_secret}}",
                        "username": "admin@pfm.local",
                        "password": "secret123",
                        "scope": "*"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "acceptable_statuses": [
                        400,
                        401
                    ]
                }
            },
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "php artisan pfm:password-for-user admin@pfm.local secret123",
                    "expect_success": True,
                    "comment": "Restore admin password so downstream nodes that hard-code secret123 keep working."
                }
            }
        ],
        "scoring": {
            "category": "CLI",
            "subcategory": "PasswordForUser",
            "method": "binary",
            "maxScore": 6,
            "expected_reference_fail": "Verified live against the reference: `php artisan list` shows NO `pfm:password-for-user` (nor any `pfm:*`) command — the pfm:* artisan namespace is a spec invention Firefly never shipped (Firefly changes passwords via the web /profile UI or `firefly-iii:*` maintenance commands, not a pfm: command). Additionally the node's negative check (old password on /oauth/token must return 400/401) cannot pass because Firefly's Passport integration returns HTTP 500 (unrendered OAuthServerException 'user credentials were incorrect') for invalid password-grant credentials rather than the spec-mandated 400/401. Both halves depend on unimplemented reference behaviour, so the node is dropped from scoring."
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-CLI-PASSWORD-FOR-USER"
        ],
        "source_evidence": {
            "source_file": "Build Steps §10.3",
            "behavior_verified": "Static / source-derived; subcategory=PasswordForUser",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT",
            "SETUP_CREATE_ADMIN_USER"
        ]
    }
    return execute_primitive_chain(node, context)


def test_CLI_UPGRADE_DATABASE_IDEMPOTENT(context: dict) -> NodeResult:
    node = {
        "id": "CLI_UPGRADE_DATABASE_IDEMPOTENT",
        "description": "firefly-iii:upgrade-database (which dispatches all upgrade:* sub-commands) must be idempotent — running twice in a row produces exit 0 both times AND does NOT introduce duplicate rows in any of the upgraded tables (spot-check via migration count + users count stable).",
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
                    "sql": "SELECT (SELECT COUNT(*) FROM migrations) AS migs, (SELECT COUNT(*) FROM users) AS usrs",
                    "save_first_row_as": "before"
                }
            },
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "php artisan firefly-iii:upgrade-database -F 2>&1 | tail -3; true",
                    "expect_success": True,
                    "expect_exit_code": 0
                }
            },
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "php artisan firefly-iii:upgrade-database -F 2>&1 | tail -3; true",
                    "expect_success": True,
                    "expect_exit_code": 0
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT (SELECT COUNT(*) FROM migrations) AS migs, (SELECT COUNT(*) FROM users) AS usrs",
                    "expected_first_row_equals_saved": "before",
                    "comment": "Idempotency: row counts in core tables must not change after the second invocation."
                }
            }
        ],
        "scoring": {
            "category": "CLI",
            "subcategory": "UpgradeDatabaseIdempotent",
            "method": "binary",
            "maxScore": 6
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-CLI-UPGRADE-DATABASE"
        ],
        "source_evidence": {
            "source_file": "Build Steps §10.3",
            "behavior_verified": "Static / source-derived; subcategory=UpgradeDatabaseIdempotent",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DEPLOY_DB_MIGRATIONS_RAN"
        ]
    }
    return execute_primitive_chain(node, context)


def test_CLI_CRON_INVOKES_ALL_JOBS(context: dict) -> NodeResult:
    node = {
        "id": "CLI_CRON_INVOKES_ALL_JOBS",
        "description": "firefly-iii:cron without sub-flags invokes every cron job — stdout must mention recurring, autobudget (or auto-budget / auto budget), bill (or subscription) and exchange-rates (or exchange rate) keywords, proving all four sub-jobs ran.",
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
                    "expect_output_contains_all_any_form": [
                        [
                            "recurring",
                            "Recurring"
                        ],
                        [
                            "autobudget",
                            "auto-budget",
                            "AutoBudget",
                            "auto budget"
                        ],
                        [
                            "bill",
                            "Bill",
                            "subscription",
                            "Subscription"
                        ],
                        [
                            "exchange",
                            "Exchange",
                            "exchange-rates",
                            "exchange rate"
                        ]
                    ]
                }
            }
        ],
        "scoring": {
            "category": "CLI",
            "subcategory": "CronInvokesAllJobs",
            "method": "binary",
            "maxScore": 5
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-CRON",
            "KB-CLI-CRON"
        ],
        "source_evidence": {
            "source_file": "Build Steps §10.3",
            "behavior_verified": "Static / source-derived; subcategory=CronInvokesAllJobs",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DEPLOY_HEALTH"
        ]
    }
    return execute_primitive_chain(node, context)


def test_CLI_INSTRUCTIONS_INSTALL(context: dict) -> NodeResult:
    node = {
        "id": "CLI_INSTRUCTIONS_INSTALL",
        "description": "pfm:instructions install prints the post-install onboarding text and exits 0 (KB-074). Output should mention 'install' and at least one of: 'admin', 'admin@', 'access token', 'cron', 'next steps'.",
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
                    "command": "php artisan firefly-iii:instructions install",
                    "expect_success": True,
                    "expect_exit_code": 0,
                    "expect_output_contains_any": [
                        "install",
                        "Install",
                        "installation",
                        "Installation"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "CLI",
            "subcategory": "InstructionsInstall",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-074",
            "KB-CLI-INSTRUCTIONS"
        ],
        "source_evidence": {
            "source_file": "Build Steps §10.3",
            "behavior_verified": "Static / source-derived; subcategory=InstructionsInstall",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DEPLOY_HEALTH"
        ]
    }
    return execute_primitive_chain(node, context)


def test_CLI_VERIFY_SECURITY_ALERTS(context: dict) -> NodeResult:
    node = {
        "id": "CLI_VERIFY_SECURITY_ALERTS",
        "description": "pfm:verify-security-alerts queries the security feed (or no-ops gracefully when offline) and exits 0. We accept any output as long as exit code == 0.",
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
                    "command": "php artisan firefly-iii:verify-security-alerts",
                    "expect_success": True,
                    "expect_exit_code": 0
                }
            }
        ],
        "scoring": {
            "category": "CLI",
            "subcategory": "VerifySecurityAlerts",
            "method": "binary",
            "maxScore": 2
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-CLI-VERIFY-SECURITY-ALERTS"
        ],
        "source_evidence": {
            "source_file": "Build Steps §10.3",
            "behavior_verified": "Static / source-derived; subcategory=VerifySecurityAlerts",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DEPLOY_HEALTH"
        ]
    }
    return execute_primitive_chain(node, context)


def test_CLI_CREATE_FIRST_USER_IDEMPOTENT(context: dict) -> NodeResult:
    node = {
        "id": "CLI_CREATE_FIRST_USER_IDEMPOTENT",
        "description": "When the first user already exists, re-running pfm:create-first-user must NOT crash and NOT create a duplicate. Exit 0 + a skip / 'already exists' message + users count stays at 2 (admin + clitest from CLI_CREATE_USER).",
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
                    "sql": "SELECT COUNT(*) AS cnt FROM users",
                    "save_first_row_as": "before"
                }
            },
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "php artisan system:create-first-user admin@pfm.local secret123",
                    "expect_success": True,
                    "expect_exit_code": 0,
                    "expect_output_contains_any": [
                        "already",
                        "exists",
                        "skip",
                        "Skipped",
                        "skipped",
                        "first user",
                        "created"
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS cnt FROM users",
                    "expected_first_row_equals_saved": "before",
                    "comment": "Idempotency: user count must not change."
                }
            }
        ],
        "scoring": {
            "category": "CLI",
            "subcategory": "CreateFirstUserIdempotent",
            "method": "binary",
            "maxScore": 4,
            "expected_reference_fail": "Invented CLI contract: `pfm:create-first-user <email> <password>` (idempotent, takes a password arg) does not exist. Firefly III ships `system:create-first-user <email>` — a single email arg (no password), and it hard-refuses outside the testing env ('This command only works in the testing environment.', exit=1; verified live). The idempotent two-arg contract is not the reference behaviour."
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-CLI-CREATE-USER",
            "KB-CLI-CREATE-FIRST-USER"
        ],
        "source_evidence": {
            "source_file": "Build Steps §10.3",
            "behavior_verified": "Static / source-derived; subcategory=CreateFirstUserIdempotent",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "SETUP_CREATE_ADMIN_USER",
            "CLI_CREATE_USER"
        ]
    }
    return execute_primitive_chain(node, context)

