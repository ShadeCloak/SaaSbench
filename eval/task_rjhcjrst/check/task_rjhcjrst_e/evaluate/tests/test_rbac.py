
from __future__ import annotations

from ..utils import NodeResult
from ._common import execute_primitive_chain


def test_RBAC_SETUP_USER_OWNER(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_SETUP_USER_OWNER",
        "description": "Provision owner_user@pfm.local; user is auto-assigned UserRoleEnum::OWNER of their own default group; additionally insert group_memberships row giving them OWNER role inside group_a (the admin's shared group). Triggers HandlesNewUserRegistration for default-group + OWNER membership.",
        "primitive_chain": [
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "cd /var/www/html && php _make_rbac_user.php owner_user@pfm.local owner admin@pfm.local",
                    "expect_success": True,
                    "expect_output_contains": "OK email="
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS cnt FROM group_memberships gm JOIN users u ON u.id=gm.user_id JOIN user_roles ur ON ur.id=gm.user_role_id JOIN user_groups ug ON ug.id=gm.user_group_id WHERE u.email='owner_user@pfm.local' AND ur.title='owner' AND ug.title='admin@pfm.local'",
                    "expected_result": {
                        "cnt": 1
                    }
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "Setup",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=Setup",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_SETUP_USER_FULL(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_SETUP_USER_FULL",
        "description": "Provision full_user@pfm.local with UserRoleEnum::FULL membership in group_a (admin's default group). FULL escalates almost everything except removing creator/deleting the group itself.",
        "primitive_chain": [
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "cd /var/www/html && php _make_rbac_user.php full_user@pfm.local full admin@pfm.local",
                    "expect_success": True,
                    "expect_output_contains": "OK email="
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT ur.title AS role FROM group_memberships gm JOIN users u ON u.id=gm.user_id JOIN user_roles ur ON ur.id=gm.user_role_id JOIN user_groups ug ON ug.id=gm.user_group_id WHERE u.email='full_user@pfm.local' AND ug.title='admin@pfm.local'",
                    "expected_result": {
                        "role": "full"
                    }
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "Setup",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=Setup",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_SETUP_USER_RO(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_SETUP_USER_RO",
        "description": "Provision ro_user@pfm.local with UserRoleEnum::READ_ONLY ('ro') membership in group_a. RO can read most resources but cannot perform any state-changing action.",
        "primitive_chain": [
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "cd /var/www/html && php _make_rbac_user.php ro_user@pfm.local ro admin@pfm.local",
                    "expect_success": True,
                    "expect_output_contains": "OK email="
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT ur.title AS role FROM group_memberships gm JOIN users u ON u.id=gm.user_id JOIN user_roles ur ON ur.id=gm.user_role_id JOIN user_groups ug ON ug.id=gm.user_group_id WHERE u.email='ro_user@pfm.local' AND ug.title='admin@pfm.local'",
                    "expected_result": {
                        "role": "ro"
                    }
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "Setup",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=Setup",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_SETUP_USER_MNG_TRX(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_SETUP_USER_MNG_TRX",
        "description": "Provision mng_trx_user@pfm.local with UserRoleEnum::MANAGE_TRANSACTIONS ('mng_trx') membership in group_a. mng_trx is the granular role for transaction CRUD.",
        "primitive_chain": [
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "cd /var/www/html && php _make_rbac_user.php mng_trx_user@pfm.local mng_trx admin@pfm.local",
                    "expect_success": True,
                    "expect_output_contains": "OK email="
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT ur.title AS role FROM group_memberships gm JOIN users u ON u.id=gm.user_id JOIN user_roles ur ON ur.id=gm.user_role_id JOIN user_groups ug ON ug.id=gm.user_group_id WHERE u.email='mng_trx_user@pfm.local' AND ug.title='admin@pfm.local'",
                    "expected_result": {
                        "role": "mng_trx"
                    }
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "Setup",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=Setup",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_SETUP_USER_MNG_BUDGETS(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_SETUP_USER_MNG_BUDGETS",
        "description": "Provision mng_budgets_user@pfm.local with UserRoleEnum::MANAGE_BUDGETS ('mng_budgets') membership in group_a.",
        "primitive_chain": [
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "cd /var/www/html && php _make_rbac_user.php mng_budgets_user@pfm.local mng_budgets admin@pfm.local",
                    "expect_success": True,
                    "expect_output_contains": "OK email="
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT ur.title AS role FROM group_memberships gm JOIN users u ON u.id=gm.user_id JOIN user_roles ur ON ur.id=gm.user_role_id JOIN user_groups ug ON ug.id=gm.user_group_id WHERE u.email='mng_budgets_user@pfm.local' AND ug.title='admin@pfm.local'",
                    "expected_result": {
                        "role": "mng_budgets"
                    }
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "Setup",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=Setup",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_SETUP_USER_READ_BUDGETS(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_SETUP_USER_READ_BUDGETS",
        "description": "Provision read_budgets_user@pfm.local with UserRoleEnum::READ_BUDGETS ('read_budgets') membership in group_a (granular read-only on budgets).",
        "primitive_chain": [
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "cd /var/www/html && php _make_rbac_user.php read_budgets_user@pfm.local read_budgets admin@pfm.local",
                    "expect_success": True,
                    "expect_output_contains": "OK email="
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT ur.title AS role FROM group_memberships gm JOIN users u ON u.id=gm.user_id JOIN user_roles ur ON ur.id=gm.user_role_id JOIN user_groups ug ON ug.id=gm.user_group_id WHERE u.email='read_budgets_user@pfm.local' AND ug.title='admin@pfm.local'",
                    "expected_result": {
                        "role": "read_budgets"
                    }
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "Setup",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=Setup",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_SETUP_USER_VIEW_REPORTS(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_SETUP_USER_VIEW_REPORTS",
        "description": "Provision view_reports_user@pfm.local with UserRoleEnum::VIEW_REPORTS ('view_reports') membership in group_a.",
        "primitive_chain": [
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "cd /var/www/html && php _make_rbac_user.php view_reports_user@pfm.local view_reports admin@pfm.local",
                    "expect_success": True,
                    "expect_output_contains": "OK email="
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT ur.title AS role FROM group_memberships gm JOIN users u ON u.id=gm.user_id JOIN user_roles ur ON ur.id=gm.user_role_id JOIN user_groups ug ON ug.id=gm.user_group_id WHERE u.email='view_reports_user@pfm.local' AND ug.title='admin@pfm.local'",
                    "expected_result": {
                        "role": "view_reports"
                    }
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "Setup",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=Setup",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_SETUP_USER_VIEW_MEMBERSHIPS(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_SETUP_USER_VIEW_MEMBERSHIPS",
        "description": "Provision view_memberships_user@pfm.local with UserRoleEnum::VIEW_MEMBERSHIPS ('view_memberships') membership in group_a. Can view memberships+roles but cannot manage them (managing requires FULL/OWNER).",
        "primitive_chain": [
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "cd /var/www/html && php _make_rbac_user.php view_memberships_user@pfm.local view_memberships admin@pfm.local",
                    "expect_success": True,
                    "expect_output_contains": "OK email="
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT ur.title AS role FROM group_memberships gm JOIN users u ON u.id=gm.user_id JOIN user_roles ur ON ur.id=gm.user_role_id JOIN user_groups ug ON ug.id=gm.user_group_id WHERE u.email='view_memberships_user@pfm.local' AND ug.title='admin@pfm.local'",
                    "expected_result": {
                        "role": "view_memberships"
                    }
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "Setup",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=Setup",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_SETUP_GROUP_B_ISOLATION(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_SETUP_GROUP_B_ISOLATION",
        "description": "Provision a SECOND tenant: alice_user@pfm.local. Registration auto-creates her default UserGroup titled 'alice_user@pfm.local' with alice as OWNER. She has NO membership in group_a, so all group_a resources must be invisible (404, not 403) to her.",
        "primitive_chain": [
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "cd /var/www/html && php _make_rbac_user.php alice_user@pfm.local _NONE_",
                    "expect_success": True,
                    "expect_output_contains": "OK email="
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT ug.title AS group_title, ur.title AS role FROM group_memberships gm JOIN users u ON u.id=gm.user_id JOIN user_groups ug ON ug.id=gm.user_group_id JOIN user_roles ur ON ur.id=gm.user_role_id WHERE u.email='alice_user@pfm.local'",
                    "expected_result": {
                        "group_title": "alice_user@pfm.local",
                        "role": "owner"
                    }
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS cnt FROM group_memberships gm JOIN users u ON u.id=gm.user_id JOIN user_groups ug ON ug.id=gm.user_group_id WHERE u.email='alice_user@pfm.local' AND ug.title='admin@pfm.local'",
                    "expected_result": {
                        "cnt": 0
                    }
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "Setup",
            "method": "binary",
            "maxScore": 2
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054",
            "KB-055"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=Setup",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_OWNER_CAN_LIST_ACCOUNTS(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_OWNER_CAN_LIST_ACCOUNTS",
        "description": "[allow] OWNER can list all accounts in group_a. AccountController@index does not restrict by sub-role; OWNER trivially passes.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_owner",
                    "username": "owner_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/accounts",
                    "headers": {
                        "Authorization": "Bearer {{rbac_owner_token}}",
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "OwnerAllow",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=OwnerAllow",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_OWNER"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_OWNER_CAN_CREATE_BUDGET(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_OWNER_CAN_CREATE_BUDGET",
        "description": "[allow] OWNER can create a budget — short-circuits all $acceptedRoles checks. Verifies the OWNER short-circuit in hasRoleInGroupOrOwner().",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_owner",
                    "username": "owner_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/budgets",
                    "headers": {
                        "Authorization": "Bearer {{rbac_owner_token}}",
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "name": "OwnerBudget_RBAC_alpha",
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
                "type": "P06",
                "inputs": {
                    "required_fields": [
                        "data"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "OwnerAllow",
            "method": "binary",
            "maxScore": 2
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=OwnerAllow",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_OWNER"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_FULL_CAN_PURGE_DATA(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_FULL_CAN_PURGE_DATA",
        "description": "[allow] FULL role passes the DELETE /api/v1/data endpoint (purge data). Per PRD §8.7 example #19, FULL is treated as a group-level superuser for almost every action.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_full",
                    "username": "full_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/budgets",
                    "headers": {
                        "Authorization": "Bearer {{rbac_full_token}}",
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "FullAllow",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=FullAllow",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_FULL"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_RO_CAN_LIST_ACCOUNTS(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_RO_CAN_LIST_ACCOUNTS",
        "description": "[allow pair to RBAC_RO_CANNOT_*] READ_ONLY ('ro') CAN GET /api/v1/accounts. Per PRD §8.7 example #4, the list endpoint accepts READ_ONLY.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_ro",
                    "username": "ro_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/accounts",
                    "headers": {
                        "Authorization": "Bearer {{rbac_ro_token}}",
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "ReadOnlyAllow",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=ReadOnlyAllow",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_RO"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_RO_CANNOT_CREATE_ACCOUNT(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_RO_CANNOT_CREATE_ACCOUNT",
        "description": "[deny pair] READ_ONLY CANNOT POST /api/v1/accounts. Per PRD §8.7 example #5, AccountFormRequest::$acceptedRoles=[MANAGE_TRANSACTIONS] does not include 'ro' → 403 (in-group denial). 404 also accepted by P14 semantics.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_ro",
                    "username": "ro_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P14",
                "inputs": {
                    "role": "ro",
                    "action": "POST /api/v1/accounts",
                    "token": "{{rbac_ro_token}}",
                    "body": {
                        "name": "RO_AttemptAccount",
                        "type": "asset",
                        "currency_code": "USD",
                        "opening_balance": "0",
                        "opening_balance_date": "2025-01-01"
                    },
                    "expected_result": "denied",
                    "expected_status": 403,
                    "_p14_accepts": [
                        403,
                        404
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "ReadOnlyDeny",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054",
            "KB-055"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=ReadOnlyDeny",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_RO"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_RO_CANNOT_CREATE_BUDGET(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_RO_CANNOT_CREATE_BUDGET",
        "description": "[deny pair] READ_ONLY CANNOT POST /api/v1/budgets. BudgetFormRequest::$acceptedRoles=[MANAGE_BUDGETS] excludes 'ro' → 403.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_ro",
                    "username": "ro_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P14",
                "inputs": {
                    "role": "ro",
                    "action": "POST /api/v1/budgets",
                    "token": "{{rbac_ro_token}}",
                    "body": {
                        "name": "RO_AttemptBudget",
                        "active": True
                    },
                    "expected_result": "denied",
                    "expected_status": 403,
                    "_p14_accepts": [
                        403,
                        404
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "ReadOnlyDeny",
            "method": "binary",
            "maxScore": 3,
            "expected_reference_fail": "Firefly III does NOT enforce fine-grained UserRole (ro/mng_trx/read_budgets/view_reports) denial for this resource operation at the API layer — verified live: the restricted user's active administration IS group 'admin@pfm.local' with ONLY the restricted role (users.user_group_id=1), yet the request returns 200/allowed. Firefly's API enforces coarse owner/full gating (owner-only ops like membership/config DO get denied) but treats granular sub-roles as a data-model concern, not an API guard. The flat per-resource RBAC-denial model is invented; the reference cannot exhibit it."
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054",
            "KB-055"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=ReadOnlyDeny",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_RO"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_RO_CANNOT_DELETE_TRANSACTION(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_RO_CANNOT_DELETE_TRANSACTION",
        "description": "[deny pair] READ_ONLY CANNOT DELETE a transaction. TransactionGroupDeleteRequest::$acceptedRoles=[MANAGE_TRANSACTIONS] excludes 'ro' → 403; or 404 if the transaction id used does not belong to a group ro_user can see.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_ro",
                    "username": "ro_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P14",
                "inputs": {
                    "role": "ro",
                    "action": "DELETE /api/v1/transactions/{{seed_transaction_id}}",
                    "token": "{{rbac_ro_token}}",
                    "expected_result": "denied",
                    "expected_status": 403,
                    "_p14_accepts": [
                        403,
                        404
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "ReadOnlyDeny",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054",
            "KB-055"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=ReadOnlyDeny",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_RO"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_MNG_TRX_CAN_CREATE_TRANSACTION(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_MNG_TRX_CAN_CREATE_TRANSACTION",
        "description": "[allow pair] MANAGE_TRANSACTIONS CAN POST /api/v1/transactions. Direct match in TransactionStoreRequest::$acceptedRoles.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_mng_trx",
                    "username": "mng_trx_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/accounts",
                    "no_auto_capture": True,
                    "capture_to_context": {
                        "context_key": "rbac_mngtrx_asset_id",
                        "json_path": "$.data.id"
                    },
                    "headers": {
                        "Authorization": "Bearer {{rbac_mng_trx_token}}",
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "name": "mng_trx base asset {{run_id}}",
                        "type": "asset",
                        "account_role": "defaultAsset"
                    }
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/accounts",
                    "no_auto_capture": True,
                    "capture_to_context": {
                        "context_key": "rbac_mngtrx_expense_id",
                        "json_path": "$.data.id"
                    },
                    "headers": {
                        "Authorization": "Bearer {{rbac_mng_trx_token}}",
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "name": "mng_trx base expense {{run_id}}",
                        "type": "expense"
                    }
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/transactions",
                    "headers": {
                        "Authorization": "Bearer {{rbac_mng_trx_token}}",
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "group_title": "RBAC_MngTrx_Withdraw",
                        "transactions": [
                            {
                                "type": "withdrawal",
                                "date": "2025-06-01",
                                "amount": "10.00",
                                "description": "RBAC_MNG_TRX_proof",
                                "source_id": "{{rbac_mngtrx_asset_id}}",
                                "destination_id": "{{rbac_mngtrx_expense_id}}"
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
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "MngTrxAllow",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=MngTrxAllow",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_MNG_TRX"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_MNG_TRX_CANNOT_CREATE_BUDGET(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_MNG_TRX_CANNOT_CREATE_BUDGET",
        "description": "[deny pair] MANAGE_TRANSACTIONS CANNOT POST /api/v1/budgets. Per PRD §8.7 example #7, budgets require MANAGE_BUDGETS, not mng_trx → 403.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_mng_trx",
                    "username": "mng_trx_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P14",
                "inputs": {
                    "role": "mng_trx",
                    "action": "POST /api/v1/budgets",
                    "token": "{{rbac_mng_trx_token}}",
                    "body": {
                        "name": "MngTrx_AttemptBudget",
                        "active": True
                    },
                    "expected_result": "denied",
                    "expected_status": 403,
                    "_p14_accepts": [
                        403,
                        404
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "MngTrxDeny",
            "method": "binary",
            "maxScore": 3,
            "expected_reference_fail": "Firefly III does NOT enforce fine-grained UserRole (ro/mng_trx/read_budgets/view_reports) denial for this resource operation at the API layer — verified live: the restricted user's active administration IS group 'admin@pfm.local' with ONLY the restricted role (users.user_group_id=1), yet the request returns 200/allowed. Firefly's API enforces coarse owner/full gating (owner-only ops like membership/config DO get denied) but treats granular sub-roles as a data-model concern, not an API guard. The flat per-resource RBAC-denial model is invented; the reference cannot exhibit it."
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054",
            "KB-055"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=MngTrxDeny",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_MNG_TRX"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_MNG_TRX_CANNOT_CREATE_RULE(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_MNG_TRX_CANNOT_CREATE_RULE",
        "description": "[deny pair] MANAGE_TRANSACTIONS CANNOT POST /api/v1/rules. Rules require MANAGE_RULES → 403.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_mng_trx",
                    "username": "mng_trx_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P14",
                "inputs": {
                    "role": "mng_trx",
                    "action": "POST /api/v1/rules",
                    "token": "{{rbac_mng_trx_token}}",
                    "body": {
                        "title": "MngTrx_AttemptRule",
                        "rule_group_id": "{{seed_rule_group_id}}",
                        "trigger": "store-journal",
                        "triggers": [
                            {
                                "type": "description_is",
                                "value": "x"
                            }
                        ],
                        "actions": [
                            {
                                "type": "set_category",
                                "value": "x"
                            }
                        ]
                    },
                    "expected_result": "denied",
                    "expected_status": 403,
                    "_p14_accepts": [
                        403,
                        404
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "MngTrxDeny",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054",
            "KB-055"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=MngTrxDeny",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_MNG_TRX"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_MNG_TRX_CAN_LIST_BUDGETS(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_MNG_TRX_CAN_LIST_BUDGETS",
        "description": "[allow] MANAGE_TRANSACTIONS CAN GET /api/v1/budgets (read-side). Per spec, mng_trx implies basic read access to other group resources for transaction context (e.g. selecting a budget when posting a transaction). Index endpoints generally accept any in-group membership.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_mng_trx",
                    "username": "mng_trx_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/budgets",
                    "headers": {
                        "Authorization": "Bearer {{rbac_mng_trx_token}}",
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "MngTrxAllow",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=MngTrxAllow",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_MNG_TRX"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_MNG_BUDGETS_CAN_CREATE_BUDGET(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_MNG_BUDGETS_CAN_CREATE_BUDGET",
        "description": "[allow pair] MANAGE_BUDGETS CAN POST /api/v1/budgets. Per PRD §8.7 example #8, direct match.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_mng_budgets",
                    "username": "mng_budgets_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/budgets",
                    "headers": {
                        "Authorization": "Bearer {{rbac_mng_budgets_token}}",
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "name": "MngBudgets_RBAC_beta",
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
                            "path": "$.data.attributes.name",
                            "expected": "MngBudgets_RBAC_beta"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "MngBudgetsAllow",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=MngBudgetsAllow",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_MNG_BUDGETS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_MNG_BUDGETS_CANNOT_CREATE_TRANSACTION(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_MNG_BUDGETS_CANNOT_CREATE_TRANSACTION",
        "description": "[deny pair] MANAGE_BUDGETS CANNOT POST /api/v1/transactions. Transactions require MANAGE_TRANSACTIONS → 403.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_mng_budgets",
                    "username": "mng_budgets_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P14",
                "inputs": {
                    "role": "mng_budgets",
                    "action": "POST /api/v1/transactions",
                    "token": "{{rbac_mng_budgets_token}}",
                    "body": {
                        "transactions": [
                            {
                                "type": "withdrawal",
                                "date": "2025-06-01",
                                "amount": "5.00",
                                "description": "MngBudgets_AttemptTrx",
                                "source_id": "{{seed_asset_account_id}}",
                                "destination_id": "{{seed_expense_account_id}}"
                            }
                        ]
                    },
                    "expected_result": "denied",
                    "expected_status": 403,
                    "_p14_accepts": [
                        403,
                        404
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "MngBudgetsDeny",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054",
            "KB-055"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=MngBudgetsDeny",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_MNG_BUDGETS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_MNG_BUDGETS_CAN_CREATE_BUDGETLIMIT(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_MNG_BUDGETS_CAN_CREATE_BUDGETLIMIT",
        "description": "[allow] MANAGE_BUDGETS CAN POST /api/v1/budgets/{id}/limits. BudgetLimit is part of the budget aggregate; same role gates.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_mng_budgets",
                    "username": "mng_budgets_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/budgets",
                    "no_auto_capture": True,
                    "capture_to_context": {
                        "context_key": "rbac_mngbudgets_budget_id",
                        "json_path": "$.data.id"
                    },
                    "headers": {
                        "Authorization": "Bearer {{rbac_mng_budgets_token}}",
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "name": "mng_budgets base budget {{run_id}}"
                    }
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/budgets/{{rbac_mngbudgets_budget_id}}/limits",
                    "headers": {
                        "Authorization": "Bearer {{rbac_mng_budgets_token}}",
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "start": "2025-06-01",
                        "end": "2025-06-30",
                        "amount": "300.00",
                        "currency_code": "USD"
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
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "MngBudgetsAllow",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=MngBudgetsAllow",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_MNG_BUDGETS",
            "RBAC_MNG_BUDGETS_CAN_CREATE_BUDGET"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_READ_BUDGETS_CAN_LIST_BUDGETS(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_READ_BUDGETS_CAN_LIST_BUDGETS",
        "description": "[allow pair] READ_BUDGETS CAN GET /api/v1/budgets. Direct match for the granular read role.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_read_budgets",
                    "username": "read_budgets_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/budgets",
                    "headers": {
                        "Authorization": "Bearer {{rbac_read_budgets_token}}",
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "ReadBudgetsAllow",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=ReadBudgetsAllow",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_READ_BUDGETS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_READ_BUDGETS_CANNOT_CREATE_BUDGET(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_READ_BUDGETS_CANNOT_CREATE_BUDGET",
        "description": "[deny pair] READ_BUDGETS CANNOT POST /api/v1/budgets — read-only on budgets, write requires MANAGE_BUDGETS → 403.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_read_budgets",
                    "username": "read_budgets_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P14",
                "inputs": {
                    "role": "read_budgets",
                    "action": "POST /api/v1/budgets",
                    "token": "{{rbac_read_budgets_token}}",
                    "body": {
                        "name": "ReadBudgets_AttemptBudget",
                        "active": True
                    },
                    "expected_result": "denied",
                    "expected_status": 403,
                    "_p14_accepts": [
                        403,
                        404
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "ReadBudgetsDeny",
            "method": "binary",
            "maxScore": 3,
            "expected_reference_fail": "Firefly III does NOT enforce fine-grained UserRole (ro/mng_trx/read_budgets/view_reports) denial for this resource operation at the API layer — verified live: the restricted user's active administration IS group 'admin@pfm.local' with ONLY the restricted role (users.user_group_id=1), yet the request returns 200/allowed. Firefly's API enforces coarse owner/full gating (owner-only ops like membership/config DO get denied) but treats granular sub-roles as a data-model concern, not an API guard. The flat per-resource RBAC-denial model is invented; the reference cannot exhibit it."
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054",
            "KB-055"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=ReadBudgetsDeny",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_READ_BUDGETS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_READ_BUDGETS_CANNOT_LIST_RULES(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_READ_BUDGETS_CANNOT_LIST_RULES",
        "description": "[deny] READ_BUDGETS CANNOT GET /api/v1/rules. Out-of-scope read also denied — granular read roles do NOT extend to other resources → 403.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_read_budgets",
                    "username": "read_budgets_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P14",
                "inputs": {
                    "role": "read_budgets",
                    "action": "GET /api/v1/rules",
                    "token": "{{rbac_read_budgets_token}}",
                    "expected_result": "denied",
                    "expected_status": 403,
                    "_p14_accepts": [
                        403,
                        404
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "ReadBudgetsDeny",
            "method": "binary",
            "maxScore": 3,
            "expected_reference_fail": "Firefly III does NOT enforce fine-grained UserRole (ro/mng_trx/read_budgets/view_reports) denial for this resource operation at the API layer — verified live: the restricted user's active administration IS group 'admin@pfm.local' with ONLY the restricted role (users.user_group_id=1), yet the request returns 200/allowed. Firefly's API enforces coarse owner/full gating (owner-only ops like membership/config DO get denied) but treats granular sub-roles as a data-model concern, not an API guard. The flat per-resource RBAC-denial model is invented; the reference cannot exhibit it."
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054",
            "KB-055"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=ReadBudgetsDeny",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_READ_BUDGETS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_VIEW_REPORTS_CAN_GET_INSIGHT(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_VIEW_REPORTS_CAN_GET_INSIGHT",
        "description": "[allow pair] VIEW_REPORTS CAN GET /api/v1/insight/expense/total (or /api/v1/reports/...). Per PRD §8.7 example #17, direct match.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_view_reports",
                    "username": "view_reports_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/insight/expense/total?start=2025-01-01&end=2025-12-31",
                    "headers": {
                        "Authorization": "Bearer {{rbac_view_reports_token}}",
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "ViewReportsAllow",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=ViewReportsAllow",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_VIEW_REPORTS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_VIEW_REPORTS_CANNOT_CREATE_BUDGET(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_VIEW_REPORTS_CANNOT_CREATE_BUDGET",
        "description": "[deny pair] VIEW_REPORTS CANNOT POST /api/v1/budgets — only granted reporting view, not budget write → 403.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_view_reports",
                    "username": "view_reports_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P14",
                "inputs": {
                    "role": "view_reports",
                    "action": "POST /api/v1/budgets",
                    "token": "{{rbac_view_reports_token}}",
                    "body": {
                        "name": "ViewReports_AttemptBudget",
                        "active": True
                    },
                    "expected_result": "denied",
                    "expected_status": 403,
                    "_p14_accepts": [
                        403,
                        404
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "ViewReportsDeny",
            "method": "binary",
            "maxScore": 2,
            "expected_reference_fail": "Firefly III does NOT enforce fine-grained UserRole (ro/mng_trx/read_budgets/view_reports) denial for this resource operation at the API layer — verified live: the restricted user's active administration IS group 'admin@pfm.local' with ONLY the restricted role (users.user_group_id=1), yet the request returns 200/allowed. Firefly's API enforces coarse owner/full gating (owner-only ops like membership/config DO get denied) but treats granular sub-roles as a data-model concern, not an API guard. The flat per-resource RBAC-denial model is invented; the reference cannot exhibit it."
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054",
            "KB-055"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=ViewReportsDeny",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_VIEW_REPORTS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_VIEW_MEMBERSHIPS_CAN_LIST_MEMBERS(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_VIEW_MEMBERSHIPS_CAN_LIST_MEMBERS",
        "description": "[allow pair] VIEW_MEMBERSHIPS CAN GET /api/v1/user-groups/{group_a_id}/memberships. Per PRD §8.7 example #18, direct match.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_view_mem",
                    "username": "view_memberships_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/user-groups/{{group_a_id}}/memberships",
                    "headers": {
                        "Authorization": "Bearer {{rbac_view_mem_token}}",
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 200
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "ViewMembershipsAllow",
            "method": "binary",
            "maxScore": 1,
            "expected_reference_fail": "Endpoint absent in this Firefly build: GET /api/v1/user-groups/{id}/memberships returns 404 (no memberships sub-route registered). The show endpoint exposes members:[] with can_see_members:false — the reference provides no functional member-listing API to test the view_memberships role against."
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=ViewMembershipsAllow",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_VIEW_MEMBERSHIPS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_VIEW_MEMBERSHIPS_CANNOT_INVITE(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_VIEW_MEMBERSHIPS_CANNOT_INVITE",
        "description": "[deny pair] VIEW_MEMBERSHIPS CANNOT manage memberships (POST /admin/users/invite or PUT /api/v1/user-groups/{id}/update-membership). Per PRD §8.6 'managing memberships still requires FULL or OWNER' → 403.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_view_mem",
                    "username": "view_memberships_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P14",
                "inputs": {
                    "role": "view_memberships",
                    "action": "PUT /api/v1/user-groups/{{group_a_id}}/update-membership",
                    "token": "{{rbac_view_mem_token}}",
                    "body": {
                        "email": "newmember@pfm.local",
                        "roles": [
                            "ro"
                        ]
                    },
                    "expected_result": "denied",
                    "expected_status": 403,
                    "_p14_accepts": [
                        403,
                        404
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "ViewMembershipsDeny",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054",
            "KB-055"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=ViewMembershipsDeny",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_VIEW_MEMBERSHIPS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_USER_B_CANNOT_SEE_USER_A_ACCOUNT(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_USER_B_CANNOT_SEE_USER_A_ACCOUNT",
        "description": "[multi-tenant 404 hide] alice (group_b OWNER) requests GET /api/v1/accounts/{group_a_account_id}. routeBinder filters by auth()->user()->user_group_id; resource not found in alice's group → 404 NotFoundHttpException (NOT 403). Verifies KB-055 cross-group hide-existence rule.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_alice",
                    "username": "alice_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/accounts/{{seed_asset_account_id}}",
                    "headers": {
                        "Authorization": "Bearer {{rbac_alice_token}}",
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 404
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "MultiTenantHide",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-009",
            "KB-055"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=MultiTenantHide",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_GROUP_B_ISOLATION"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_USER_B_CANNOT_DELETE_USER_A_BUDGET(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_USER_B_CANNOT_DELETE_USER_A_BUDGET",
        "description": "[multi-tenant 404 hide] alice tries DELETE /api/v1/budgets/{group_a_budget_id} → 404 (binder cannot find it via her group_memberships). Even DELETE on a foreign resource hides existence with 404, not 403.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_alice",
                    "username": "alice_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "DELETE",
                    "path": "/api/v1/budgets/{{rbac_owner_created_budget_id}}",
                    "headers": {
                        "Authorization": "Bearer {{rbac_alice_token}}",
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 404
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "MultiTenantHide",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-009",
            "KB-055"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=MultiTenantHide",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_GROUP_B_ISOLATION",
            "RBAC_OWNER_CAN_CREATE_BUDGET"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_USER_B_CANNOT_LIST_GROUP_A_RESOURCES(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_USER_B_CANNOT_LIST_GROUP_A_RESOURCES",
        "description": "[multi-tenant scope] alice's GET /api/v1/accounts returns 200 BUT $.data array contains only her own group_b accounts (zero or one). Repository scopes by user_group_id; cross-group rows never surface even in collection responses.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_alice",
                    "username": "alice_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/accounts?type=asset&limit=100",
                    "headers": {
                        "Authorization": "Bearer {{rbac_alice_token}}",
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
                            "path": "$.data[*].attributes.name",
                            "_check": "every name MUST NOT equal admin's seeded asset account name",
                            "must_not_contain": "{{seed_asset_account_name}}"
                        },
                        {
                            "path": "$.data.length",
                            "_check": "alice has at most her own seeded accounts (likely 0)",
                            "max": 5
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "MultiTenantScope",
            "method": "binary",
            "maxScore": 4
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-055"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=MultiTenantScope",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_GROUP_B_ISOLATION"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_GROUP_SWITCH_USE_ENDPOINT(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_GROUP_SWITCH_USE_ENDPOINT",
        "description": "[multi-tenant context] full_user is a member of BOTH her own default group AND group_a. POST /api/v1/user-groups/{group_a_id}/use validates membership and switches active group; subsequent GET /api/v1/about/user reflects user_group_id == group_a_id.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_full",
                    "username": "full_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/user-groups/{{group_a_id}}/use",
                    "headers": {
                        "Authorization": "Bearer {{rbac_full_token}}",
                        "Accept": "application/json"
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
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/about/user",
                    "headers": {
                        "Authorization": "Bearer {{rbac_full_token}}",
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.data.attributes.user_group_id",
                            "expected": "{{group_a_id}}"
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "MultiTenantSwitch",
            "method": "binary",
            "maxScore": 4,
            "expected_reference_fail": "Endpoint absent in this Firefly build: POST /api/v1/user-groups/{id}/use (group-switch) is COMMENTED OUT in routes/api.php (verified: only index/show/update routes are registered; store/use/update-membership/destroy are disabled) — returns 404. The group-switch API does not exist in the reference."
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=MultiTenantSwitch",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_FULL"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_DEFAULT_GROUP_ON_REGISTRATION(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_DEFAULT_GROUP_ON_REGISTRATION",
        "description": "[multi-tenant onboarding] After alice_user registration, user_groups MUST contain a row title='alice_user@pfm.local' AND group_memberships MUST contain a row (alice_id, that_group_id, role='owner'). Verifies HandlesNewUserRegistration::createGroupMembership() default-group + OWNER membership creation.",
        "primitive_chain": [
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT ug.title AS group_title, ur.title AS role, u.email AS owner_email FROM users u JOIN group_memberships gm ON gm.user_id=u.id JOIN user_groups ug ON ug.id=gm.user_group_id JOIN user_roles ur ON ur.id=gm.user_role_id WHERE u.email='alice_user@pfm.local' AND ug.title='alice_user@pfm.local'",
                    "expected_result": {
                        "group_title": "alice_user@pfm.local",
                        "role": "owner",
                        "owner_email": "alice_user@pfm.local"
                    }
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT u.user_group_id IS NOT NULL AS has_default_group FROM users u WHERE u.email='alice_user@pfm.local'",
                    "expected_result": {
                        "has_default_group": 1
                    }
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "MultiTenantOnboard",
            "method": "binary",
            "maxScore": 4
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=MultiTenantOnboard",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_GROUP_B_ISOLATION"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_OWNER_CANNOT_BE_REMOVED_FROM_OWN_GROUP(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_OWNER_CANNOT_BE_REMOVED_FROM_OWN_GROUP",
        "description": "[multi-tenant invariant] PRD §8.6 FULL-role definition: 'except remove/change original creator and delete group itself'. Even FULL cannot remove the OWNER from group_a. Attempt to PUT /api/v1/user-groups/{group_a_id}/update-membership demoting admin's OWNER membership to 'ro' or removing must be rejected (403/422).",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_full",
                    "username": "full_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P14",
                "inputs": {
                    "role": "full",
                    "action": "PUT /api/v1/user-groups/{{group_a_id}}/update-membership",
                    "token": "{{rbac_full_token}}",
                    "body": {
                        "email": "admin@pfm.local",
                        "roles": []
                    },
                    "expected_result": "denied",
                    "expected_status": 403,
                    "_p14_accepts": [
                        403,
                        422,
                        404
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "MultiTenantInvariant",
            "method": "binary",
            "maxScore": 4
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=MultiTenantInvariant",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_FULL"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_ADMIN_CAN_LIST_USERS(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_ADMIN_CAN_LIST_USERS",
        "description": "[admin allow] Global owner-role user CAN GET /api/v1/users. Endpoint is gated by 'api-admin' middleware (IsAdminApi), which checks User::hasRole('owner') against the global roles+role_user pivot.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "admin",
                    "username": "admin@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/users",
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
                "type": "P06",
                "inputs": {
                    "required_fields": [
                        "data"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "AdminApiAllow",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=AdminApiAllow",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_NON_ADMIN_CANNOT_LIST_USERS(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_NON_ADMIN_CANNOT_LIST_USERS",
        "description": "[admin deny pair] ro_user (no global 'owner' role) CANNOT GET /api/v1/users. IsAdminApi throws AuthorizationException → 403 with body containing 'No access to this resource.'",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_ro",
                    "username": "ro_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P14",
                "inputs": {
                    "role": "ro",
                    "action": "GET /api/v1/users",
                    "token": "{{rbac_ro_token}}",
                    "expected_result": "denied",
                    "expected_status": 403,
                    "_p14_accepts": [
                        403,
                        404
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "AdminApiDeny",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=AdminApiDeny",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_RO"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_ADMIN_CAN_PUT_CONFIGURATION(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_ADMIN_CAN_PUT_CONFIGURATION",
        "description": "[admin allow] Global owner CAN PUT /api/v1/configuration/permission_update_check (or any single-config update). Per PRD §8.7 example #1, api-admin gates this endpoint.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "admin",
                    "username": "admin@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "PUT",
                    "path": "/api/v1/configuration/configuration.permission_update_check",
                    "headers": {
                        "Authorization": "Bearer {{admin_token}}",
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    "body": {
                        "value": True
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
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "AdminApiAllow",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=AdminApiAllow",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_NON_ADMIN_CANNOT_PUT_CONFIGURATION(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_NON_ADMIN_CANNOT_PUT_CONFIGURATION",
        "description": "[admin deny pair] full_user (group-level FULL but NO global owner role) CANNOT PUT /api/v1/configuration/*. Per PRD §8.7 example #2, IsAdminApi denies → 403. Confirms FULL is a group-scope superuser, NOT a global one.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "rbac_full",
                    "username": "full_user@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P14",
                "inputs": {
                    "role": "full",
                    "action": "PUT /api/v1/configuration/configuration.permission_update_check",
                    "token": "{{rbac_full_token}}",
                    "body": {
                        "value": False
                    },
                    "expected_result": "denied",
                    "expected_status": 403,
                    "_p14_accepts": [
                        401,
                        403,
                        404
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "AdminApiDeny",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=AdminApiDeny",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "RBAC_SETUP_USER_FULL"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_ADMIN_CAN_ENABLE_CURRENCY(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_ADMIN_CAN_ENABLE_CURRENCY",
        "description": "[admin allow] Global owner CAN POST /api/v1/currencies/JPY/enable. Currency enable/disable is also gated by api-admin (per PRD §8.7 example #16). Verifies admin path; non-admin path covered by RBAC_NON_ADMIN_CANNOT_PUT_CONFIGURATION as a parallel deny pair for the api-admin middleware.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "method": "api_token",
                    "role": "admin",
                    "username": "admin@pfm.local",
                    "password": "EvalRBACPass123!"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/currencies/JPY/enable",
                    "headers": {
                        "Authorization": "Bearer {{admin_token}}",
                        "Accept": "application/json"
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
                    "sql": "SELECT COUNT(*) AS enabled FROM transaction_currency_user_group tcug JOIN transaction_currencies c ON c.id=tcug.transaction_currency_id JOIN users u ON u.user_group_id=tcug.user_group_id WHERE c.code='JPY' AND u.email='admin@pfm.local'",
                    "expected_result": {
                        "enabled": 1
                    },
                    "comment": "Firefly persists currency enablement per user-group in the transaction_currency_user_group pivot (a row = enabled), NOT in the legacy transaction_currencies.enabled column, which the API's `enabled` attribute is no longer derived from. The enable endpoint inserts a pivot row for the caller's group."
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "AdminApiAllow",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "marketplace_rbac",
        "_kb_refs": [
            "KB-054"
        ],
        "source_evidence": {
            "source_file": "User & Permissions §8",
            "behavior_verified": "Static / source-derived; subcategory=AdminApiAllow",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_FULL_CAN_CREATE_TRANSACTION(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_FULL_CAN_CREATE_TRANSACTION",
        "description": "Group role 'full' can create transactions (allow side of full role's broad permissions)",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "full"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/accounts",
                    "no_auto_capture": True,
                    "capture_to_context": {
                        "context_key": "rbac_full_asset_id",
                        "json_path": "$.data.id"
                    },
                    "body": {
                        "name": "full base asset {{run_id}}",
                        "type": "asset",
                        "account_role": "defaultAsset"
                    }
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/accounts",
                    "no_auto_capture": True,
                    "capture_to_context": {
                        "context_key": "rbac_full_expense_id",
                        "json_path": "$.data.id"
                    },
                    "body": {
                        "name": "full base expense {{run_id}}",
                        "type": "expense"
                    }
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/transactions",
                    "body": {
                        "transactions": [
                            {
                                "type": "withdrawal",
                                "source_id": "{{rbac_full_asset_id}}",
                                "destination_id": "{{rbac_full_expense_id}}",
                                "amount": "10.00",
                                "date": "2025-04-01",
                                "description": "rbac full allow"
                            }
                        ]
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
                            "path": "$.data",
                            "expected_present": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "FullRoleAllow",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "marketplace_rbac",
        "source_evidence": {
            "source_file": "RBAC §8",
            "behavior_verified": "full role parity test"
        },
        "prereqs": [
            "RBAC_SETUP_USER_FULL",
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_MNG_PIGGIES_CAN_CREATE_PIGGYBANK(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_MNG_PIGGIES_CAN_CREATE_PIGGYBANK",
        "description": "Group role 'mng_piggies' can create piggy banks",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "mng_piggies"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/accounts",
                    "no_auto_capture": True,
                    "capture_to_context": {
                        "context_key": "rbac_piggy_asset_id",
                        "json_path": "$.data.id"
                    },
                    "body": {
                        "name": "mng_piggies base asset {{run_id}}",
                        "type": "asset",
                        "account_role": "defaultAsset"
                    }
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/piggy-banks",
                    "body": {
                        "name": "rbac piggy",
                        "target_amount": "100",
                        "transaction_currency_id": 1,
                        "start_date": "2025-01-01",
                        "accounts": [
                            {
                                "account_id": "{{rbac_piggy_asset_id}}"
                            }
                        ]
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 201
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.data",
                            "expected_present": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "PiggyBanksAllow",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "marketplace_rbac",
        "source_evidence": {
            "source_file": "RBAC §8",
            "behavior_verified": "mng_piggies role allow test"
        },
        "prereqs": [
            "RBAC_SETUP_USER_MNG_BUDGETS",
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_MNG_RULES_CAN_CREATE_RULE(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_MNG_RULES_CAN_CREATE_RULE",
        "description": "Group role 'mng_rules' can create rules",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "mng_rules"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/rule-groups",
                    "no_auto_capture": True,
                    "capture_to_context": {
                        "context_key": "rbac_rule_group_id",
                        "json_path": "$.data.id"
                    },
                    "body": {
                        "title": "mng_rules base group {{run_id}}"
                    }
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/rules",
                    "body": {
                        "title": "rbac rule",
                        "rule_group_id": "{{rbac_rule_group_id}}",
                        "trigger": "store-journal",
                        "triggers": [
                            {
                                "type": "description_contains",
                                "value": "x"
                            }
                        ],
                        "actions": [
                            {
                                "type": "add_tag",
                                "value": "y"
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
                            "path": "$.data",
                            "expected_present": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "RulesAllow",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "marketplace_rbac",
        "source_evidence": {
            "source_file": "RBAC §8",
            "behavior_verified": "mng_rules role allow test"
        },
        "prereqs": [
            "RBAC_SETUP_USER_MNG_BUDGETS",
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_MNG_WEBHOOKS_CAN_CREATE_WEBHOOK(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_MNG_WEBHOOKS_CAN_CREATE_WEBHOOK",
        "description": "Group role 'mng_webhooks' can create webhooks",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "mng_webhooks"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "POST",
                    "path": "/api/v1/webhooks",
                    "body": {
                        "title": "rbac webhook",
                        "url": "http://192.168.224.2:9001/hook",
                        "triggers": ["STORE_TRANSACTION"],
                        "responses": ["TRANSACTIONS"],
                        "deliveries": ["JSON"]
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 201
                }
            },
            {
                "type": "P07",
                "inputs": {
                    "assertions": [
                        {
                            "path": "$.data",
                            "expected_present": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "WebhooksAllow",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "marketplace_rbac",
        "source_evidence": {
            "source_file": "RBAC §8",
            "behavior_verified": "mng_webhooks role allow test"
        },
        "prereqs": [
            "RBAC_SETUP_USER_MNG_BUDGETS",
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_RBAC_READ_PIGGIES_CAN_LIST_PIGGYBANKS(context: dict) -> NodeResult:
    node = {
        "id": "RBAC_READ_PIGGIES_CAN_LIST_PIGGYBANKS",
        "description": "Group role 'read_piggies' can list piggy banks",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "read_piggies"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/piggy-banks"
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
                            "path": "$.data",
                            "expected_present": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "RBAC",
            "subcategory": "ReadPiggiesAllow",
            "method": "binary",
            "maxScore": 2
        },
        "complexity_tier": "marketplace_rbac",
        "source_evidence": {
            "source_file": "RBAC §8",
            "behavior_verified": "read_piggies role allow test"
        },
        "prereqs": [
            "RBAC_SETUP_USER_READ_BUDGETS",
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)

