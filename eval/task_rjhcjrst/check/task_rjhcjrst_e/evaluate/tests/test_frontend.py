
from __future__ import annotations

from ..utils import NodeResult
from ._common import execute_primitive_chain


def test_FRONTEND_DASHBOARD_LOADS(context: dict) -> NodeResult:
    node = {
        "id": "FRONTEND_DASHBOARD_LOADS",
        "description": "Dashboard page renders for an authenticated user — must show a navbar, a sidebar/aside, and an h1/h2 containing 'Dashboard' (or the user's i18n equivalent). Verifies the v1 AdminLTE shell or v2 Bootstrap-5 shell is wired up end-to-end behind session auth.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin",
                    "session_required": True,
                    "comment": "Web routes (/dashboard) use session cookies, not Bearer."
                }
            },
            {
                "type": "P18",
                "inputs": {
                    "steps": [
                        {
                            "action": "goto",
                            "url": "/login"
                        },
                        {
                            "action": "fill",
                            "selector": "input[name=email]",
                            "value": "admin@pfm.local"
                        },
                        {
                            "action": "fill",
                            "selector": "input[name=password]",
                            "value": "secret123"
                        },
                        {
                            "action": "click",
                            "selector": "button[type=submit]"
                        },
                        {
                            "action": "wait",
                            "ms": 1500
                        },
                        {
                            "action": "goto",
                            "url": "/dashboard"
                        },
                        {
                            "action": "wait",
                            "ms": 1000
                        }
                    ]
                }
            },
            {
                "type": "P19",
                "inputs": {
                    "url": "/",
                    "assertions": [
                        {
                            "selector": "nav.navbar, nav.main-header, header nav",
                            "shouldExist": True,
                            "comment": "AdminLTE v1 uses .main-header; v2/Bootstrap may use nav.navbar — accept either."
                        },
                        {
                            "selector": ".sidebar, aside, .main-sidebar",
                            "shouldExist": True
                        },
                        {
                            "selector": "h1, h2, .content-header h1",
                            "textContains": "Dashboard",
                            "caseInsensitive": True,
                            "i18nFallback": [
                                "Dashboard",
                                "Tableau de bord",
                                "Übersicht",
                                "Panel"
                            ]
                        },
                        {
                            "selector": "main, .content-wrapper, #content",
                            "shouldExist": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "Frontend",
            "subcategory": "DashboardRendering",
            "method": "weighted",
            "maxScore": 4
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": True
        },
        "_kb_refs": [
            "KB-068",
            "KB-FRONTEND-LAYOUT",
            "KB-DASHBOARD-ROUTE"
        ],
        "source_evidence": {
            "source_file": "Frontend §7",
            "behavior_verified": "Static / source-derived; subcategory=DashboardRendering",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT",
            "DEPLOY_HEALTH",
            "SETUP_CREATE_ADMIN_USER"
        ]
    }
    return execute_primitive_chain(node, context)


def test_FRONTEND_ACCOUNTS_LIST_RENDERS(context: dict) -> NodeResult:
    node = {
        "id": "FRONTEND_ACCOUNTS_LIST_RENDERS",
        "description": "GET /accounts/asset renders the asset-account index table — at least one .account-row must be present after we created EvalSrcAsset/EvalDestExpense in DAG-C. Verifies the AccountController index route + Twig/Blade table partial.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin",
                    "session_required": True
                }
            },
            {
                "type": "P18",
                "inputs": {
                    "steps": [
                        {
                            "action": "goto",
                            "url": "/login"
                        },
                        {
                            "action": "fill",
                            "selector": "input[name=email]",
                            "value": "admin@pfm.local"
                        },
                        {
                            "action": "fill",
                            "selector": "input[name=password]",
                            "value": "secret123"
                        },
                        {
                            "action": "click",
                            "selector": "button[type=submit]"
                        },
                        {
                            "action": "wait",
                            "ms": 1500
                        },
                        {
                            "action": "goto",
                            "url": "/accounts/asset"
                        },
                        {
                            "action": "wait",
                            "ms": 1000
                        }
                    ]
                }
            },
            {
                "type": "P19",
                "inputs": {
                    "url": "/accounts/asset",
                    "assertions": [
                        {
                            "selector": "table.account-list, table.table, table#accounts-table",
                            "shouldExist": True,
                            "comment": "v1 uses table.table (Bootstrap 3); v2 may carry .account-list class — accept either."
                        },
                        {
                            "selector": "table tbody tr, .account-row, tr[data-account-id]",
                            "minCount": 1,
                            "comment": "At least one rendered account row."
                        },
                        {
                            "selector": "th, .table thead th",
                            "minCount": 3,
                            "comment": "Header has Name + Type + Balance columns at minimum."
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "Frontend",
            "subcategory": "AccountListTable",
            "method": "weighted",
            "maxScore": 4
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": True
        },
        "_kb_refs": [
            "KB-FRONTEND-ACCOUNTS-INDEX",
            "KB-068"
        ],
        "source_evidence": {
            "source_file": "Frontend §7",
            "behavior_verified": "Static / source-derived; subcategory=AccountListTable",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "FRONTEND_DASHBOARD_LOADS",
            "API_ACCOUNT_CREATE"
        ]
    }
    return execute_primitive_chain(node, context)


def test_FRONTEND_TRANSACTION_CREATE_FORM(context: dict) -> NodeResult:
    node = {
        "id": "FRONTEND_TRANSACTION_CREATE_FORM",
        "description": "GET /transactions/create/withdrawal renders the Vue 2 (v1) or Alpine.js (v2) transaction-create form. The form must expose the four required input/select controls so the user can create a withdrawal: description, source account, destination account, amount.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin",
                    "session_required": True
                }
            },
            {
                "type": "P18",
                "inputs": {
                    "steps": [
                        {
                            "action": "goto",
                            "url": "/login"
                        },
                        {
                            "action": "fill",
                            "selector": "input[name=email]",
                            "value": "admin@pfm.local"
                        },
                        {
                            "action": "fill",
                            "selector": "input[name=password]",
                            "value": "secret123"
                        },
                        {
                            "action": "click",
                            "selector": "button[type=submit]"
                        },
                        {
                            "action": "wait",
                            "ms": 1500
                        },
                        {
                            "action": "goto",
                            "url": "/transactions/create/withdrawal"
                        },
                        {
                            "action": "wait",
                            "ms": 2000,
                            "comment": "Vue/Alpine hydration takes a moment."
                        }
                    ]
                }
            },
            {
                "type": "P19",
                "inputs": {
                    "url": "/transactions/create/withdrawal",
                    "assertions": [
                        {
                            "selector": "form, #create-form, form.create-transaction",
                            "shouldExist": True
                        },
                        {
                            "selector": "input[name=description], input[name='transactions[0][description]'], input[id*=description]",
                            "shouldExist": True
                        },
                        {
                            "selector": "select[name=source_id], input[name='transactions[0][source_name]'], input[id*=source]",
                            "shouldExist": True
                        },
                        {
                            "selector": "select[name=destination_id], input[name='transactions[0][destination_name]'], input[id*=destination]",
                            "shouldExist": True
                        },
                        {
                            "selector": "input[name=amount], input[name='transactions[0][amount]'], input[type=number], input[id*=amount]",
                            "shouldExist": True
                        },
                        {
                            "selector": "button[type=submit], button.btn-success, input[type=submit]",
                            "shouldExist": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "Frontend",
            "subcategory": "TransactionCreateForm",
            "method": "weighted",
            "maxScore": 5
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": True
        },
        "_kb_refs": [
            "KB-FRONTEND-TXN-CREATE",
            "KB-VUE-CREATE-TRANSACTION"
        ],
        "source_evidence": {
            "source_file": "Frontend §7",
            "behavior_verified": "Static / source-derived; subcategory=TransactionCreateForm",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "FRONTEND_DASHBOARD_LOADS",
            "API_ACCOUNT_CREATE"
        ]
    }
    return execute_primitive_chain(node, context)


def test_FRONTEND_2FA_ENABLE_QR_PAGE(context: dict) -> NodeResult:
    node = {
        "id": "FRONTEND_2FA_ENABLE_QR_PAGE",
        "description": "GET /profile/mfa/enable renders the TOTP enrollment page — must show an SVG QR code (rendered server-side by bacon/bacon-qr-code), an input field for the one-time password, and a <code>/<pre> element with the base32 secret so the user can manually enter it into apps that don't scan QR.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin",
                    "session_required": True
                }
            },
            {
                "type": "P18",
                "inputs": {
                    "steps": [
                        {
                            "action": "goto",
                            "url": "/login"
                        },
                        {
                            "action": "fill",
                            "selector": "input[name=email]",
                            "value": "admin@pfm.local"
                        },
                        {
                            "action": "fill",
                            "selector": "input[name=password]",
                            "value": "secret123"
                        },
                        {
                            "action": "click",
                            "selector": "button[type=submit]"
                        },
                        {
                            "action": "wait",
                            "ms": 1500
                        },
                        {
                            "action": "goto",
                            "url": "/profile/mfa/enable"
                        },
                        {
                            "action": "wait",
                            "ms": 1000
                        }
                    ]
                }
            },
            {
                "type": "P19",
                "inputs": {
                    "url": "/mfa/enableMFA",
                    "assertions": [
                        {
                            "selector": "svg, img[src*='data:image/svg'], img[src*='qr']",
                            "shouldExist": True,
                            "comment": "QR is rendered as inline SVG by bacon-qr-code, may also appear as data URI image."
                        },
                        {
                            "selector": "input[name=one_time_password], input[name=code], input[name=mfa_code]",
                            "shouldExist": True
                        },
                        {
                            "selector": "code, pre, .secret, span.mfa-secret",
                            "shouldExist": True,
                            "comment": "Plaintext base32 secret displayed for manual entry per KB-MFA-PLAINTEXT."
                        },
                        {
                            "selector": "form, button[type=submit]",
                            "shouldExist": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "Frontend",
            "subcategory": "TwoFactorQrPage",
            "method": "weighted",
            "maxScore": 5
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": True
        },
        "_kb_refs": [
            "KB-MFA-PLAINTEXT",
            "KB-2FA-SECRET-50CHARS",
            "KB-FRONTEND-PROFILE-MFA"
        ],
        "source_evidence": {
            "source_file": "Frontend §7",
            "behavior_verified": "Static / source-derived; subcategory=TwoFactorQrPage",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "FRONTEND_DASHBOARD_LOADS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_FRONTEND_RULE_BUILDER_PAGE(context: dict) -> NodeResult:
    node = {
        "id": "FRONTEND_RULE_BUILDER_PAGE",
        "description": "GET /rules/create/{ruleGroup} renders the rule-builder form — must contain trigger and action selector controls so the user can compose a rule (description_contains -> add_tag, etc.). Rule group id is resolved from the seeded default group or the one created by API_RULE_CREATE in DAG-C.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin",
                    "session_required": True
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT MIN(rg.id) AS rg_id FROM rule_groups rg JOIN users u ON u.id=rg.user_id WHERE u.email='admin@pfm.local' AND rg.deleted_at IS NULL",
                    "save_first_row_as": "rg",
                    "comment": "Must resolve a rule group OWNED BY admin: /rules/create/{ruleGroup} uses user-scoped route-model binding, so a rule_group belonging to another seeded user 404s. Scope to admin's own smallest rule_group_id (seeded 'Rule group for subscriptions' or EvalRuleGroup created in DAG-C)."
                }
            },
            {
                "type": "P18",
                "inputs": {
                    "steps": [
                        {
                            "action": "goto",
                            "url": "/login"
                        },
                        {
                            "action": "fill",
                            "selector": "input[name=email]",
                            "value": "admin@pfm.local"
                        },
                        {
                            "action": "fill",
                            "selector": "input[name=password]",
                            "value": "secret123"
                        },
                        {
                            "action": "click",
                            "selector": "button[type=submit]"
                        },
                        {
                            "action": "wait",
                            "ms": 1500
                        },
                        {
                            "action": "goto",
                            "url": "/rules/create/{{rg.rg_id}}"
                        },
                        {
                            "action": "wait",
                            "ms": 1500
                        }
                    ]
                }
            },
            {
                "type": "P19",
                "inputs": {
                    "url": "/rules/create/{{rg.rg_id}}",
                    "assertions": [
                        {
                            "selector": "form, form#store-rule, form.rule-form",
                            "shouldExist": True
                        },
                        {
                            "selector": "input[name=title], input[id=title]",
                            "shouldExist": True
                        },
                        {
                            "selector": "select[name*='triggers'], select[name*='trigger_type'], .rule-trigger select, [data-rule-trigger]",
                            "shouldExist": True,
                            "minCount": 1,
                            "comment": "Trigger row selector — Vue 2 in v1 may render dynamic select.rule-trigger."
                        },
                        {
                            "selector": "select[name*='actions'], select[name*='action_type'], .rule-action select, [data-rule-action]",
                            "shouldExist": True,
                            "minCount": 1
                        },
                        {
                            "selector": "button[type=submit], input[type=submit]",
                            "shouldExist": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "Frontend",
            "subcategory": "RuleBuilderForm",
            "method": "weighted",
            "maxScore": 5
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": True
        },
        "_kb_refs": [
            "KB-RULE-ACTIONS-31",
            "KB-FRONTEND-RULES"
        ],
        "source_evidence": {
            "source_file": "Frontend §7",
            "behavior_verified": "Static / source-derived; subcategory=RuleBuilderForm",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "FRONTEND_DASHBOARD_LOADS",
            "API_RULE_CREATE"
        ]
    }
    return execute_primitive_chain(node, context)


def test_FRONTEND_BUDGETS_DRAGDROP_REORDER(context: dict) -> NodeResult:
    node = {
        "id": "FRONTEND_BUDGETS_DRAGDROP_REORDER",
        "description": "GET /budgets renders the budget index with drag-and-drop reorder support — must contain a sortable handle element AND a Sortable.js bootstrap script (script[id=sortable-budgets] or window.Sortable.create call). Verifies the AdminLTE Sortable wiring documented in §7 of task.md.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin",
                    "session_required": True
                }
            },
            {
                "type": "P18",
                "inputs": {
                    "steps": [
                        {
                            "action": "goto",
                            "url": "/login"
                        },
                        {
                            "action": "fill",
                            "selector": "input[name=email]",
                            "value": "admin@pfm.local"
                        },
                        {
                            "action": "fill",
                            "selector": "input[name=password]",
                            "value": "secret123"
                        },
                        {
                            "action": "click",
                            "selector": "button[type=submit]"
                        },
                        {
                            "action": "wait",
                            "ms": 1500
                        },
                        {
                            "action": "goto",
                            "url": "/budgets"
                        },
                        {
                            "action": "wait",
                            "ms": 1000
                        }
                    ]
                }
            },
            {
                "type": "P19",
                "inputs": {
                    "url": "/budgets",
                    "assertions": [
                        {
                            "selector": ".sortable-handle, .handle, .drag-handle, [data-sortable]",
                            "shouldExist": True,
                            "comment": "Drag handle element class used by Sortable.js."
                        },
                        {
                            "selector": "script#sortable-budgets, script[src*='sortable'], script[src*='Sortable']",
                            "shouldExist": True,
                            "comment": "Sortable.js library or page-specific bootstrap script must be included."
                        },
                        {
                            "selector": "table.budget-list, table tbody, .budget-row, ul.sortable",
                            "shouldExist": True
                        },
                        {
                            "selector": "a[href*='/budgets/create'], button[href*='/budgets/create']",
                            "shouldExist": True
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "Frontend",
            "subcategory": "BudgetSortable",
            "method": "weighted",
            "maxScore": 4
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": True
        },
        "_kb_refs": [
            "KB-FRONTEND-BUDGET-SORTABLE",
            "KB-068"
        ],
        "source_evidence": {
            "source_file": "Frontend §7",
            "behavior_verified": "Static / source-derived; subcategory=BudgetSortable",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "FRONTEND_DASHBOARD_LOADS",
            "API_BUDGET_CREATE"
        ]
    }
    return execute_primitive_chain(node, context)


def test_FRONTEND_LANGUAGE_SWITCH(context: dict) -> NodeResult:
    node = {
        "id": "FRONTEND_LANGUAGE_SWITCH",
        "description": "Switching the user's language preference to de_DE (via PUT /api/v1/preferences/language) re-renders /dashboard with html lang='de' (or 'de-DE'). Verifies the i18n preference -> HTML lang attribute round-trip + Twig/Blade @lang() rebinding documented in PRD §7.",
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
                    "path": "/api/v1/preferences/language",
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "Authorization": "Bearer {{admin_pat}}"
                    },
                    "body": {
                        "data": "de_DE"
                    },
                    "comment": "PFM stores the preference in the preferences table keyed by user_id+name='language'."
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "acceptable_statuses": [
                        200,
                        201,
                        204
                    ]
                }
            },
            {
                "type": "P18",
                "inputs": {
                    "steps": [
                        {
                            "action": "goto",
                            "url": "/login"
                        },
                        {
                            "action": "fill",
                            "selector": "input[name=email]",
                            "value": "admin@pfm.local"
                        },
                        {
                            "action": "fill",
                            "selector": "input[name=password]",
                            "value": "secret123"
                        },
                        {
                            "action": "click",
                            "selector": "button[type=submit]"
                        },
                        {
                            "action": "wait",
                            "ms": 1500
                        },
                        {
                            "action": "goto",
                            "url": "/dashboard"
                        },
                        {
                            "action": "wait",
                            "ms": 1000
                        }
                    ]
                }
            },
            {
                "type": "P19",
                "inputs": {
                    "url": "/",
                    "assertions": [
                        {
                            "selector": "html",
                            "attribute": "lang",
                            "valueRegex": "^de(-DE|_DE)?$",
                            "comment": "Accept de, de-DE, or de_DE."
                        }
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT CAST(data AS CHAR) AS data FROM preferences p JOIN users u ON u.id=p.user_id WHERE u.email='admin@pfm.local' AND p.name='language'",
                    "additional_assertions": [
                        {
                            "field": "data",
                            "match_type": "contains",
                            "expected": "de_DE"
                        }
                    ],
                    "comment": "Persisted preference value must contain de_DE. Firefly stores preference values JSON-encoded, so the raw column is the string '\"de_DE\"' (with quotes); a contains match against the actual `data` column is the honest check (the previous expected_first_row key 'data_contains' never matched a real column and so silently failed)."
                }
            }
        ],
        "scoring": {
            "category": "Frontend",
            "subcategory": "LanguagePreferenceRoundtrip",
            "method": "weighted",
            "maxScore": 6
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": True
        },
        "_kb_refs": [
            "KB-I18N-LANGS",
            "KB-PREFERENCES-TABLE"
        ],
        "source_evidence": {
            "source_file": "Frontend §7",
            "behavior_verified": "Static / source-derived; subcategory=LanguagePreferenceRoundtrip",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "FRONTEND_DASHBOARD_LOADS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_FRONTEND_LAYOUT_BLADE_FILE_EXISTS(context: dict) -> NodeResult:
    node = {
        "id": "FRONTEND_LAYOUT_BLADE_FILE_EXISTS",
        "description": "The main app layout file resources/views/layouts/app.blade.php (or the Twig equivalent at resources/views/layouts/v1/default.twig / resources/views/layouts/v2/default.twig) must exist on disk — KB-068 anchor for the layout extension hierarchy.",
        "primitive_chain": [
            {
                "type": "P01",
                "inputs": {
                    "any_of": [
                        "resources/views/layouts/app.blade.php",
                        "resources/views/layouts/default.twig",
                        "resources/views/v1/layout/default.twig",
                        "resources/views/v2/layout/default.twig",
                        "resources/views/layout/default.twig",
                        "resources/views/layout/v2/default.twig",
                        "resources/views/layout/v3/default.twig"
                    ],
                    "in_container": True,
                    "type": "file",
                    "comment": "Layout root may live under any of these names depending on whether v1, v2 or both are shipped."
                }
            },
            {
                "type": "P02",
                "inputs": {
                    "path_any_of": [
                        "resources/views/layouts/app.blade.php",
                        "resources/views/layouts/default.twig",
                        "resources/views/v1/layout/default.twig",
                        "resources/views/v2/layout/default.twig",
                        "resources/views/layout/default.twig",
                        "resources/views/layout/v2/default.twig",
                        "resources/views/layout/v3/default.twig"
                    ],
                    "in_container": True,
                    "match_type": "regex",
                    "pattern": "(@yield|\\{%\\s*block|<body)"
                }
            }
        ],
        "scoring": {
            "category": "Frontend",
            "subcategory": "LayoutFileExists",
            "method": "weighted",
            "maxScore": 2
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-068",
            "KB-FRONTEND-LAYOUT"
        ],
        "source_evidence": {
            "source_file": "Frontend §7",
            "behavior_verified": "Static / source-derived; subcategory=LayoutFileExists",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DEPLOY_HEALTH"
        ]
    }
    return execute_primitive_chain(node, context)

