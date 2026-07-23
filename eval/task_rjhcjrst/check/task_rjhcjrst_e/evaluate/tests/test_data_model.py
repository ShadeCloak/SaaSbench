
from __future__ import annotations

from ..utils import NodeResult
from ._common import execute_primitive_chain


def test_DB_TABLE_USERS(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_USERS",
        "description": "users table exists with all auth/2FA/multi-tenant columns required by §3.3.1.",
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
                        "users"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "users",
                    "expected_columns": [
                        "id",
                        "email",
                        "password",
                        "remember_token",
                        "blocked",
                        "blocked_code",
                        "mfa_secret",
                        "user_group_id",
                        "domain",
                        "objectguid",
                        "created_at",
                        "updated_at",
                        ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "AuthSchema",
            "method": "weighted",
            "maxScore": 5
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ENTITY-USER"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=AuthSchema",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_USER_GROUPS(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_USER_GROUPS",
        "description": "user_groups table is the multi-tenant scope owner; required for the OWNER/MEMBER model.",
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
                        "user_groups"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "user_groups",
                    "expected_columns": [
                        "id",
                        "title",
                        "created_at",
                        "updated_at",
                        "deleted_at"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "MultiTenant",
            "method": "weighted",
            "maxScore": 3
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ENTITY-USERGROUP"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=MultiTenant",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_GROUP_MEMBERSHIPS(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_GROUP_MEMBERSHIPS",
        "description": "group_memberships pivot links users ↔ user_groups ↔ user_roles for fine-grained per-resource role assignments.",
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
                        "group_memberships"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "group_memberships",
                    "expected_columns": [
                        "id",
                        "user_id",
                        "user_group_id",
                        "user_role_id",
                        "created_at",
                        "updated_at"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "MultiTenant",
            "method": "weighted",
            "maxScore": 4
        },
        "complexity_tier": "marketplace_rbac",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ENTITY-GROUPMEMBERSHIP"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=MultiTenant",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DB_TABLE_USER_GROUPS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_USER_ROLES(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_USER_ROLES",
        "description": "user_roles table is seeded with the 21 fine-grained role titles (owner, full, ro, mng_*, read_*, view_reports, view_memberships).",
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
                        "user_roles"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "user_roles",
                    "expected_columns": [
                        "id",
                        "title",
                        "created_at",
                        "updated_at"
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(DISTINCT title) AS cnt FROM user_roles WHERE title IN ('owner','full','ro','mng_trx','mng_meta','mng_budgets','mng_piggies','mng_subscriptions','mng_rules','mng_recurring','mng_webhooks','mng_currencies','read_budgets','read_piggies','read_subscriptions','read_rules','read_recurring','read_webhooks','read_currencies','view_reports','view_memberships')",
                    "expected_predicates": [
                        {
                            "field": "cnt",
                            "op": ">=",
                            "value": 21
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "RoleSeeding",
            "method": "weighted",
            "maxScore": 8
        },
        "complexity_tier": "marketplace_rbac",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-USERROLE-ENUM",
            "KB-21-ROLES"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=RoleSeeding",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_ACCOUNTS(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_ACCOUNTS",
        "description": "accounts table — the financial counterparty entity, scoped by user_group_id with virtual_balance DECIMAL(32,12).",
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
                        "accounts"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "accounts",
                    "expected_columns": [
                        "id",
                        "user_id",
                        "user_group_id",
                        "account_type_id",
                        "name",
                        "virtual_balance",
                        "iban",
                        "active",
                        "encrypted",
                        "order",
                        "created_at",
                        "updated_at",
                        "deleted_at"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "FinancialCore",
            "method": "weighted",
            "maxScore": 5
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ENTITY-ACCOUNT"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=FinancialCore",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_ACCOUNT_TYPES(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_ACCOUNT_TYPES",
        "description": "account_types reference table is seeded with all 14 AccountTypeEnum values (Asset, Expense, Revenue, Cash, CreditCard, Debt, Loan, Mortgage, Beneficiary, Import, InitialBalance, LiabilityCredit, Reconciliation, Default).",
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
                        "account_types"
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS cnt FROM account_types",
                    "expected_predicates": [
                        {
                            "field": "cnt",
                            "op": ">=",
                            "value": 14
                        }
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(DISTINCT type) AS cnt FROM account_types WHERE type IN ('Asset account','Expense account','Revenue account','Cash account','Credit card','Debt','Loan','Mortgage','Beneficiary account','Import account','Initial balance account','Liability credit account','Reconciliation account','Default account')",
                    "expected_predicates": [
                        {
                            "field": "cnt",
                            "op": ">=",
                            "value": 14
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "ReferenceData",
            "method": "weighted",
            "maxScore": 6
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ACCOUNT-TYPES-ENUM"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=ReferenceData",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_ACCOUNT_META(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_ACCOUNT_META",
        "description": "account_meta key/value table for per-account preferences (currency_id, monthly_payment_date, etc.).",
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
                        "account_meta"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "account_meta",
                    "expected_columns": [
                        "id",
                        "account_id",
                        "name",
                        "data",
                        "created_at",
                        "updated_at"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "FinancialCore",
            "method": "weighted",
            "maxScore": 3
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ENTITY-ACCOUNTMETA"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=FinancialCore",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DB_TABLE_ACCOUNTS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_TRANSACTION_GROUPS(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_TRANSACTION_GROUPS",
        "description": "transaction_groups table is the top of the three-level double-entry hierarchy (split container).",
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
                        "transaction_groups"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "transaction_groups",
                    "expected_columns": [
                        "id",
                        "user_id",
                        "user_group_id",
                        "title",
                        "created_at",
                        "updated_at",
                        "deleted_at"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "DoubleEntry",
            "method": "weighted",
            "maxScore": 4
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ENTITY-TRANSACTIONGROUP"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=DoubleEntry",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_TRANSACTION_JOURNALS(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_TRANSACTION_JOURNALS",
        "description": "transaction_journals — middle level, carries date, description, transaction_type_id, and bill_id.",
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
                        "transaction_journals"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "transaction_journals",
                    "expected_columns": [
                        "id",
                        "user_id",
                        "user_group_id",
                        "transaction_group_id",
                        "transaction_type_id",
                        "transaction_currency_id",
                        "description",
                        "date",
                        "bill_id",
                        "order",
                        "created_at",
                        "updated_at",
                        "deleted_at"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "DoubleEntry",
            "method": "weighted",
            "maxScore": 5
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ENTITY-TRANSACTIONJOURNAL"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=DoubleEntry",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DB_TABLE_TRANSACTION_GROUPS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_TRANSACTIONS(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_TRANSACTIONS",
        "description": "transactions — leaf of double-entry hierarchy, exactly two rows per journal (debit/credit) with amount + foreign_amount as DECIMAL(32,12).",
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
                        "transactions"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "transactions",
                    "expected_columns": [
                        "id",
                        "transaction_journal_id",
                        "account_id",
                        "transaction_currency_id",
                        "foreign_currency_id",
                        "amount",
                        "foreign_amount",
                        "description",
                        "identifier",
                        "reconciled",
                        "created_at",
                        "updated_at",
                        "deleted_at"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "DoubleEntry",
            "method": "weighted",
            "maxScore": 6
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ENTITY-TRANSACTION"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=DoubleEntry",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DB_TABLE_TRANSACTION_JOURNALS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_TRANSACTION_TYPES(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_TRANSACTION_TYPES",
        "description": "transaction_types reference table is seeded with the 7 TransactionTypeEnum values.",
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
                        "transaction_types"
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(DISTINCT type) AS cnt FROM transaction_types WHERE type IN ('Withdrawal','Deposit','Transfer','Opening balance','Reconciliation','Liability credit','Invalid')",
                    "expected_predicates": [
                        {
                            "field": "cnt",
                            "op": ">=",
                            "value": 7
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "ReferenceData",
            "method": "weighted",
            "maxScore": 5
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-TX-TYPES-ENUM"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=ReferenceData",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_TRANSACTION_CURRENCIES(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_TRANSACTION_CURRENCIES",
        "description": "transaction_currencies table holds ISO currencies with per-currency decimal_places (JPY=0, USD/EUR=2, KWD=3, BTC=8).",
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
                        "transaction_currencies"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "transaction_currencies",
                    "expected_columns": [
                        "id",
                        "code",
                        "name",
                        "symbol",
                        "decimal_places",
                        "enabled",
                        "created_at",
                        "updated_at",
                        "deleted_at"
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT code, decimal_places FROM transaction_currencies WHERE code IN ('JPY','USD','EUR','KWD','BTC') ORDER BY code",
                    "expected_rows_contain": [
                        {
                            "code": "JPY",
                            "decimal_places": 0
                        },
                        {
                            "code": "USD",
                            "decimal_places": 2
                        },
                        {
                            "code": "EUR",
                            "decimal_places": 2
                        },
                        {
                            "code": "KWD",
                            "decimal_places": 3
                        },
                        {
                            "code": "BTC",
                            "decimal_places": 8
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "MultiCurrency",
            "method": "weighted",
            "maxScore": 8
        },
        "complexity_tier": "high_concurrency",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-CURRENCY-DECIMALS",
            "KB-MC-INV-1"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=MultiCurrency",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_CURRENCY_EXCHANGE_RATES(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_CURRENCY_EXCHANGE_RATES",
        "description": "currency_exchange_rates supports ExchangeRateConverter lookups by (from_currency_id, to_currency_id, date).",
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
                        "currency_exchange_rates"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "currency_exchange_rates",
                    "expected_columns": [
                        "id",
                        "user_id",
                        "user_group_id",
                        "from_currency_id",
                        "to_currency_id",
                        "date",
                        "rate",
                        "created_at",
                        "updated_at",
                        "deleted_at"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "MultiCurrency",
            "method": "weighted",
            "maxScore": 4
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ENTITY-EXCHANGERATE"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=MultiCurrency",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DB_TABLE_TRANSACTION_CURRENCIES"
        ]
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_BUDGETS(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_BUDGETS",
        "description": "budgets table — category-style label, scoped by user_group_id.",
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
                        "budgets"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "budgets",
                    "expected_columns": [
                        "id",
                        "user_id",
                        "user_group_id",
                        "name",
                        "active",
                        "order",
                        "created_at",
                        "updated_at",
                        "deleted_at"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "BudgetSystem",
            "method": "weighted",
            "maxScore": 4
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ENTITY-BUDGET"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=BudgetSystem",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_BUDGET_LIMITS(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_BUDGET_LIMITS",
        "description": "budget_limits — time-window cap with start_date, end_date, amount; created by AutoBudget cron.",
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
                        "budget_limits"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "budget_limits",
                    "expected_columns": [
                        "id",
                        "budget_id",
                        "transaction_currency_id",
                        "start_date",
                        "end_date",
                        "amount",
                        "period",
                        "generated",
                        "created_at",
                        "updated_at",
                        ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "BudgetSystem",
            "method": "weighted",
            "maxScore": 4
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ENTITY-BUDGETLIMIT"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=BudgetSystem",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DB_TABLE_BUDGETS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_AUTO_BUDGETS(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_AUTO_BUDGETS",
        "description": "auto_budgets row drives AutoBudget cron strategies (reset / rollover / adjusted) on six period boundaries.",
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
                        "auto_budgets"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "auto_budgets",
                    "expected_columns": [
                        "id",
                        "budget_id",
                        "transaction_currency_id",
                        "auto_budget_type",
                        "amount",
                        "period",
                        "created_at",
                        "updated_at"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "BudgetAutomation",
            "method": "weighted",
            "maxScore": 4
        },
        "complexity_tier": "workflow_automator",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-AUTO-BUDGET-TYPES"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=BudgetAutomation",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DB_TABLE_BUDGETS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_AVAILABLE_BUDGETS(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_AVAILABLE_BUDGETS",
        "description": "available_budgets — top-line monthly cap (BD-INV-5) per user_group + currency + window.",
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
                        "available_budgets"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "available_budgets",
                    "expected_columns": [
                        "id",
                        "user_id",
                        "user_group_id",
                        "transaction_currency_id",
                        "amount",
                        "start_date",
                        "end_date",
                        "created_at",
                        "updated_at"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "BudgetSystem",
            "method": "weighted",
            "maxScore": 3
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ENTITY-AVAILABLEBUDGET"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=BudgetSystem",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_BILLS(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_BILLS",
        "description": "bills (subscriptions) — auto-match by amount range + match_string; includes extension_date_tz to honour TZ for end-date math.",
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
                        "bills"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "bills",
                    "expected_columns": [
                        "id",
                        "user_id",
                        "user_group_id",
                        "transaction_currency_id",
                        "name",
                        "match",
                        "amount_min",
                        "amount_max",
                        "date",
                        "end_date",
                        "extension_date",
                        "extension_date_tz",
                        "repeat_freq",
                        "skip",
                        "automatch",
                        "active",
                        "created_at",
                        "updated_at",
                        "deleted_at"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "BillMatching",
            "method": "weighted",
            "maxScore": 6
        },
        "complexity_tier": "workflow_automator",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ENTITY-BILL",
            "KB-BL-INV-8"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=BillMatching",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_PIGGY_BANKS(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_PIGGY_BANKS",
        "description": "piggy_banks — savings goals with target_amount DECIMAL(32,12), pivots to accounts via account_piggy_bank.",
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
                        "piggy_banks",
                        "account_piggy_bank",
                        "piggy_bank_events"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "piggy_banks",
                    "expected_columns": [
                        "id",
                        "name",
                        "target_amount",
                        "transaction_currency_id",
                        "start_date",
                        "target_date",
                        "order",
                        "active",
                        "created_at",
                        "updated_at",
                        "deleted_at"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "PiggyBanks",
            "method": "weighted",
            "maxScore": 5
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ENTITY-PIGGYBANK",
            "KB-PIVOT-ACCOUNTPIGGYBANK"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=PiggyBanks",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_RECURRENCES(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_RECURRENCES",
        "description": "recurrences template + recurrences_repetitions + recurrences_transactions feeds the CreateRecurringTransactions cron.",
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
                        "recurrences",
                        "recurrences_repetitions",
                        "recurrences_transactions",
                        "recurrences_meta",
                        "rt_meta"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "recurrences",
                    "expected_columns": [
                        "id",
                        "user_id",
                        "user_group_id",
                        "transaction_type_id",
                        "title",
                        "description",
                        "first_date",
                        "repeat_until",
                        "latest_date",
                        "repetitions",
                        "apply_rules",
                        "active",
                        "created_at",
                        "updated_at",
                        "deleted_at"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "recurrences_repetitions",
                    "expected_columns": [
                        "id",
                        "recurrence_id",
                        "repetition_type",
                        "repetition_moment",
                        "repetition_skip",
                        "weekend",
                        "created_at",
                        "updated_at"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "Recurrence",
            "method": "weighted",
            "maxScore": 6
        },
        "complexity_tier": "workflow_automator",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ENTITY-RECURRENCE",
            "KB-FIVE-REPETITIONS"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=Recurrence",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_RULES(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_RULES",
        "description": "rules + rule_groups + rule_triggers + rule_actions back the SearchRuleEngine. Rules carry strict / stop_processing / apply_on_store/update flags.",
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
                        "rules",
                        "rule_groups",
                        "rule_triggers",
                        "rule_actions"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "rules",
                    "expected_columns": [
                        "id",
                        "user_id",
                        "user_group_id",
                        "rule_group_id",
                        "title",
                        "description",
                        "order",
                        "active",
                        "stop_processing",
                        "strict",
                        "created_at",
                        "updated_at",
                        "deleted_at"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "rule_actions",
                    "expected_columns": [
                        "id",
                        "rule_id",
                        "action_type",
                        "action_value",
                        "order",
                        "active",
                        "stop_processing",
                        "created_at",
                        "updated_at"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "RuleEngine",
            "method": "weighted",
            "maxScore": 6
        },
        "complexity_tier": "workflow_automator",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ENTITY-RULE",
            "KB-RULE-ACTIONS-31"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=RuleEngine",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_WEBHOOKS(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_WEBHOOKS",
        "description": "webhooks + webhook_messages + webhook_attempts + the three pivots (webhook_webhook_trigger / response / delivery) implement the post-2025_08_19 many-to-many refactor.",
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
                        "webhooks",
                        "webhook_messages",
                        "webhook_attempts",
                        "webhook_triggers",
                        "webhook_responses",
                        "webhook_deliveries",
                        "webhook_webhook_trigger",
                        "webhook_webhook_response",
                        "webhook_webhook_delivery"
                    ]
                }
            },
            {
                "type": "P10",
                "inputs": {
                    "table": "webhooks",
                    "expected_columns": [
                        "id",
                        "user_id",
                        "user_group_id",
                        "title",
                        "secret",
                        "url",
                        "active",
                        "created_at",
                        "updated_at",
                        "deleted_at"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "Webhooks",
            "method": "weighted",
            "maxScore": 7
        },
        "complexity_tier": "workflow_automator",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ENTITY-WEBHOOK",
            "KB-WEBHOOK-TRIGGERS-8"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=Webhooks",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DB_TABLE_OAUTH_TABLES(context: dict) -> NodeResult:
    node = {
        "id": "DB_TABLE_OAUTH_TABLES",
        "description": "Five Laravel Passport tables exist: oauth_clients, oauth_access_tokens, oauth_refresh_tokens, oauth_auth_codes, oauth_personal_access_clients.",
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
                        "oauth_clients",
                        "oauth_access_tokens",
                        "oauth_refresh_tokens",
                        "oauth_auth_codes",
                        "oauth_personal_access_clients"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "OAuthSchema",
            "method": "binary",
            "maxScore": 5
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-PASSPORT-TABLES"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=OAuthSchema",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DB_INDEX_TRANSACTIONS_FK(context: dict) -> NodeResult:
    node = {
        "id": "DB_INDEX_TRANSACTIONS_FK",
        "description": "transactions table has indexes on transaction_journal_id and account_id — required for the running-balance query path that scans by account.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin"
                }
            },
            {
                "type": "P11",
                "inputs": {
                    "table": "transactions",
                    "expected_indexes": [
                        {
                            "columns": [
                                "transaction_journal_id"
                            ]
                        },
                        {
                            "columns": [
                                "account_id"
                            ]
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "Indexes",
            "method": "weighted",
            "maxScore": 4
        },
        "complexity_tier": "high_concurrency",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-INDEX-PERF"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=Indexes",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DB_TABLE_TRANSACTIONS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_DB_DECIMAL_PRECISION(context: dict) -> NodeResult:
    node = {
        "id": "DB_DECIMAL_PRECISION",
        "description": "Critical monetary columns are DECIMAL(32,12) — accounts.virtual_balance, transactions.amount, transactions.foreign_amount, bills.amount_min/max, budget_limits.amount, piggy_banks.target_amount. Verified via information_schema.",
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
                    "sql": "SELECT TABLE_NAME, COLUMN_NAME, NUMERIC_PRECISION, NUMERIC_SCALE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND ((TABLE_NAME='accounts' AND COLUMN_NAME='virtual_balance') OR (TABLE_NAME='transactions' AND COLUMN_NAME IN ('amount','foreign_amount')) OR (TABLE_NAME='bills' AND COLUMN_NAME IN ('amount_min','amount_max')) OR (TABLE_NAME='budget_limits' AND COLUMN_NAME='amount') OR (TABLE_NAME='piggy_banks' AND COLUMN_NAME='target_amount'))",
                    "expected_all_rows_match": {
                        "NUMERIC_PRECISION": 32,
                        "NUMERIC_SCALE": 12
                    }
                }
            }
        ],
        "scoring": {
            "category": "DataModel",
            "subcategory": "MoneyPrecision",
            "method": "binary",
            "maxScore": 10
        },
        "complexity_tier": "high_concurrency",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-MC-INV-1",
            "KB-DECIMAL-32-12"
        ],
        "source_evidence": {
            "source_file": "Data Model §3",
            "behavior_verified": "Static / source-derived; subcategory=MoneyPrecision",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DB_TABLE_TRANSACTIONS",
            "DB_TABLE_BILLS",
            "DB_TABLE_BUDGET_LIMITS",
            "DB_TABLE_PIGGY_BANKS"
        ]
    }
    return execute_primitive_chain(node, context)

