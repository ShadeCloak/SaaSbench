
from __future__ import annotations

from ..utils import NodeResult
from ._common import execute_primitive_chain


def test_AUTH_LOGIN_PASSWORD_GRANT(context: dict) -> NodeResult:
    node = {
        "id": "AUTH_LOGIN_PASSWORD_GRANT",
        "description": "POST /oauth/token with grant_type=password returns 200 and a JSON body containing access_token, refresh_token, token_type='Bearer'.",
        "primitive_chain": [
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
                    },
                    "timeout": 15
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            },
            {
                "type": "P06",
                "inputs": {
                    "required_fields": [
                        "access_token",
                        "refresh_token",
                        "token_type",
                        "expires_in"
                    ],
                    "field_types": {
                        "access_token": "string",
                        "expires_in": "integer"
                    }
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.token_type",
                            "expected": "Bearer"
                        },
                        {
                            "path": "$.access_token",
                            "predicate": "string_min_length",
                            "value": 20
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "Authentication",
            "subcategory": "OAuthPasswordGrant",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-OAUTH-PASSWORD-GRANT",
            "KB-PASSPORT-15-ENDPOINTS"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=OAuthPasswordGrant",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "SETUP_CREATE_ADMIN_USER",
            "SETUP_OAUTH_PASSPORT_KEYS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_AUTH_LOGIN_BAD_CREDENTIALS(context: dict) -> NodeResult:
    node = {
        "id": "AUTH_LOGIN_BAD_CREDENTIALS",
        "description": "POST /oauth/token with wrong password returns 400 (or 401) with error='invalid_grant' — verifies negative-path auth handling.",
        "primitive_chain": [
            {
                "type": "P04",
                "inputs": {
                    "no_auth": True,
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
                        "password": "wrong-password-xx",
                        "scope": "*"
                    },
                    "timeout": 10
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
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.error",
                            "expected": "invalid_grant"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "Authentication",
            "subcategory": "NegativePath",
            "method": "binary",
            "maxScore": 6,
            "expected_reference_fail": "Verified live against the reference: POST /oauth/token with a valid password client but a wrong user password returns HTTP 500 with body {message:'The user credentials were incorrect.', exception:'Laravel\\\\Passport\\\\Exceptions\\\\OAuthServerException'} (thrown at vendor/laravel/passport/src/Http/Controllers/HandlesOAuthErrors.php:26). Firefly's Passport integration does NOT render the OAuthServerException as the spec-mandated 400/401 with a JSON {error:'invalid_grant'} body — the exception bubbles to the generic 500 handler. The credentials ARE rejected (no token issued), but neither the status code nor the error-envelope shape the spec requires is implemented in the reference, so the node is dropped from scoring rather than penalising the baseline for OAuth error-rendering it never had."
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-OAUTH-ERROR-CODES"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=NegativePath",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_AUTH_PAT_USED_OK(context: dict) -> NodeResult:
    node = {
        "id": "AUTH_PAT_USED_OK",
        "description": "Calling GET /api/v1/about/user with the admin PAT (from setup) returns 200 and a JSON:API envelope identifying the admin user.",
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
                    "path": "/api/v1/about/user",
                    "headers": {
                        "Accept": "application/vnd.api+json",
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
                            "path": "$.data.attributes.email",
                            "expected": "admin@pfm.local"
                        },
                        {
                            "path": "$.data.type",
                            "expected": "users"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "Authentication",
            "subcategory": "BearerAuth",
            "method": "binary",
            "maxScore": 8
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ABOUT-USER-ENDPOINT",
            "KB-PAT-AUTH"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=BearerAuth",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "SETUP_CREATE_ACCESS_TOKEN"
        ]
    }
    return execute_primitive_chain(node, context)


def test_AUTH_BEARER_MISSING(context: dict) -> NodeResult:
    node = {
        "id": "AUTH_BEARER_MISSING",
        "description": "GET /api/v1/accounts without an Authorization header returns 401 Unauthenticated — verifies auth:api middleware is wired on the resource group.",
        "primitive_chain": [
            {
                "type": "P04",
                "inputs": {
                    "no_auth": True,
                    "method": "GET",
                    "path": "/api/v1/accounts",
                    "headers": {
                        "Accept": "application/vnd.api+json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 401
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.message",
                            "predicate": "contains",
                            "value": "Unauthenticated"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "Authentication",
            "subcategory": "MiddlewareEnforcement",
            "method": "binary",
            "maxScore": 5
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-AUTH-API-MIDDLEWARE",
            "KB-401-RESPONSE"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=MiddlewareEnforcement",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DEPLOY_HEALTH"
        ]
    }
    return execute_primitive_chain(node, context)


def test_AUTH_BEARER_INVALID(context: dict) -> NodeResult:
    node = {
        "id": "AUTH_BEARER_INVALID",
        "description": "GET /api/v1/accounts with a forged Bearer token still returns 401 — verifies token validation, not header presence.",
        "primitive_chain": [
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/accounts",
                    "headers": {
                        "Accept": "application/vnd.api+json",
                        "Authorization": "Bearer ThisIsAFakeTokenThatShouldFail0000000000000000000000000000000000"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 401
                }
            }
        ],
        "scoring": {
            "category": "Authentication",
            "subcategory": "TokenValidation",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-AUTH-API-MIDDLEWARE"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=TokenValidation",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DEPLOY_HEALTH"
        ]
    }
    return execute_primitive_chain(node, context)


def test_AUTH_2FA_SECRET_PLAINTEXT(context: dict) -> NodeResult:
    node = {
        "id": "AUTH_2FA_SECRET_PLAINTEXT",
        "description": "After enabling MFA via /api/v1/preferences (or /profile/mfa/enable), users.mfa_secret stores the 16-50 char base32 secret AS PLAINTEXT (matches ^[A-Z2-7]+$) — required by §2.7 / §5.6.3 to avoid APP_KEY coupling.",
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
                    "command": "php artisan pfm:set-mfa admin@pfm.local --enable",
                    "expect_success": True
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT mfa_secret, LENGTH(mfa_secret) AS len FROM users WHERE email='admin@pfm.local'",
                    "expected_predicates": [
                        {
                            "field": "len",
                            "op": ">=",
                            "value": 16
                        },
                        {
                            "field": "len",
                            "op": "<=",
                            "value": 50
                        },
                        {
                            "field": "mfa_secret",
                            "op": "regex",
                            "value": "^[A-Z2-7]+$"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "Authentication",
            "subcategory": "MfaSecretFormat",
            "method": "binary",
            "maxScore": 12,
            "expected_reference_fail": "Invented CLI: `pfm:set-mfa <email> --enable` does not exist — Firefly III exposes NO artisan command to enable/seed MFA (verified: no mfa command in `php artisan list`; MFA is web/API only). The tinker fallback is also unavailable in the deployed reference ('Command tinker is not defined' — the production image strips tinker)."
        },
        "complexity_tier": "high_concurrency",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-MFA-PLAINTEXT",
            "KB-2FA-SECRET-50CHARS",
            "KB-INV-2FA-1"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=MfaSecretFormat",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "AUTH_PAT_USED_OK"
        ]
    }
    return execute_primitive_chain(node, context)


def test_AUTH_OWNER_GLOBAL_ROLE(context: dict) -> NodeResult:
    node = {
        "id": "AUTH_OWNER_GLOBAL_ROLE",
        "description": "The first registered user gets the global 'owner' Role pivoted via role_user — separate from the per-group user_roles seeded for memberships.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin"
                }
            },
            {
                "type": "P09",
                "inputs": {
                    "tables": [
                        "roles",
                        "role_user"
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS cnt FROM role_user ru JOIN roles r ON r.id=ru.role_id JOIN users u ON u.id=ru.user_id WHERE r.name='owner' AND u.email='admin@pfm.local'",
                    "expected_result": {
                        "cnt": 1
                    }
                }
            }
        ],
        "scoring": {
            "category": "Authentication",
            "subcategory": "GlobalRole",
            "method": "binary",
            "maxScore": 6
        },
        "complexity_tier": "marketplace_rbac",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-OWNER-ROLE",
            "KB-PIVOT-ROLEUSER"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=GlobalRole",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "SETUP_CREATE_ADMIN_USER"
        ]
    }
    return execute_primitive_chain(node, context)


def test_AUTH_DEFAULT_USER_GROUP(context: dict) -> NodeResult:
    node = {
        "id": "AUTH_DEFAULT_USER_GROUP",
        "description": "On first login the user is automatically attached to a UserGroup whose title equals their email; user.user_group_id points to it and a group_memberships row links them with user_role.title='owner'.",
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
                    "sql": "SELECT ug.title AS group_title, u.email AS user_email, ur.title AS role_title FROM users u JOIN user_groups ug ON ug.id = u.user_group_id JOIN group_memberships gm ON gm.user_id = u.id AND gm.user_group_id = ug.id JOIN user_roles ur ON ur.id = gm.user_role_id WHERE u.email = 'admin@pfm.local'",
                    "expected_rows_contain": [
                        {
                            "group_title": "admin@pfm.local",
                            "user_email": "admin@pfm.local",
                            "role_title": "owner"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "Authentication",
            "subcategory": "MultiTenantBootstrap",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "marketplace_rbac",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-DEFAULT-GROUP-CREATION",
            "KB-INV-MT-4"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=MultiTenantBootstrap",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DB_TABLE_USER_GROUPS",
            "DB_TABLE_GROUP_MEMBERSHIPS",
            "SETUP_CREATE_ADMIN_USER"
        ]
    }
    return execute_primitive_chain(node, context)

