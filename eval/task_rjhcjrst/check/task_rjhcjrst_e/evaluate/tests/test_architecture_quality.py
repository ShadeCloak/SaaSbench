
from __future__ import annotations

import re as _re

from ..utils import NodeResult
from ._common import execute_primitive_chain
from .. import config as _config

try:
    from ..utils import db_execute as _db_execute
except Exception:
    _db_execute = None

try:
    import requests as _requests
except Exception:
    _requests = None


def _prepare_app_for_web_login(email: str, password: str) -> None:
    try:
        import subprocess as _sp
        _sp.run(
            ["docker", "exec", _config.APP_CONTAINER, "bash", "-lc",
             f"php /var/www/html/_set_password.php {email} {password} 2>/dev/null; "
             "chown -R www-data:www-data /var/www/html/storage 2>/dev/null"],
            timeout=60, capture_output=True,
        )
    except Exception:
        pass
    if _db_execute is not None:
        try:
            _db_execute(
                "UPDATE users SET mfa_secret = NULL, blocked = false WHERE email = %s",
                (email,),
            )
        except Exception:
            pass


def _fetch_web_page_authenticated(context: dict, path: str) -> None:
    context["last_response"] = None
    if _requests is None:
        return
    base = _config.APP_BASE_URL.rstrip("/")
    email = context.get("admin_email") or _config.ADMIN_EMAIL
    password = context.get("admin_password") or _config.ADMIN_PASSWORD
    _prepare_app_for_web_login(email, password)
    timeout = getattr(_config, "HTTP_TIMEOUT", 30)
    try:
        sess = _requests.Session()
        login_url = f"{base}/login"
        r = sess.get(login_url, timeout=timeout)
        m = (_re.search(r'name="_token"\s+(?:type="hidden"\s+)?value="([^"]+)"', r.text)
             or _re.search(r'name="_token"[^>]*value="([^"]+)"', r.text))
        token = m.group(1) if m else ""
        sess.post(
            login_url,
            data={"_token": token, "email": email, "password": password, "remember": "1"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=timeout,
            allow_redirects=True,
        )
        page = sess.get(
            f"{base}{path}",
            headers={"Accept": "text/html"},
            timeout=timeout,
            allow_redirects=True,
        )
        context["last_response"] = page
    except Exception:
        context["last_response"] = None


def test_ARCH_REPOSITORY_PATTERN(context: dict) -> NodeResult:
    node = {
        "id": "ARCH_REPOSITORY_PATTERN",
        "description": "LLM-judge: assess Repository pattern implementation quality — sample app/Repositories/ and app/Http/Controllers/ files, score on (a) interface/implementation separation, (b) controllers avoiding direct Eloquent calls, (c) every core entity having a Repository abstraction.",
        "primitive_chain": [
            {
                "type": "P17",
                "inputs": {
                    "evidence_type": "code_files",
                    "files_to_sample": [
                        "app/Repositories/",
                        "app/Http/Controllers/",
                        "app/Repositories/Account/",
                        "app/Repositories/Budget/",
                        "app/Repositories/TransactionGroup/"
                    ],
                    "sample_strategy": "stratified_dirs",
                    "max_files_per_dir": 4,
                    "max_total_files": 12,
                    "rubric_prompt": "You are reviewing a Laravel codebase. Score the Repository pattern implementation 0-5 across three dimensions, then sum: (1) Repository INTERFACE vs concrete implementation are separated (e.g. AccountRepositoryInterface + AccountRepository) — 0..2pt; (2) HTTP controllers depend on the interface and DO NOT call Eloquent models (->where, ->find, ->create) directly — 0..2pt; (3) every core financial entity (Account, Budget, TransactionGroup, Bill, PiggyBank, Recurrence, Rule, Webhook) has a Repository class — 0..1pt. Output JSON: {\"score\": <int 0-5>, \"reasoning\": \"<<=400 chars>>\", \"evidence\": [\"<<file:line>>\", ...]}.",
                    "score_range": [
                        0,
                        5
                    ]
                }
            }
        ],
        "scoring": {
            "category": "ArchitectureQuality",
            "subcategory": "RepositoryPattern",
            "method": "llm-judge",
            "maxScore": 18
        },
        "complexity_tier": "workflow_automator",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ARCH-REPOSITORY-PATTERN"
        ],
        "source_evidence": {
            "source_file": "Architecture §7.4",
            "behavior_verified": "Static / source-derived; subcategory=RepositoryPattern",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DEPLOY_HEALTH"
        ]
    }
    return execute_primitive_chain(node, context)


def test_ARCH_RULE_ENGINE_DESIGN(context: dict) -> NodeResult:
    node = {
        "id": "ARCH_RULE_ENGINE_DESIGN",
        "description": "LLM-judge: assess TransactionRules architecture — Action interface + Strategy pattern across the 31 action implementations + Trigger composition. Sample app/TransactionRules/Actions/, app/TransactionRules/Triggers/, app/Engines/.",
        "primitive_chain": [
            {
                "type": "P17",
                "inputs": {
                    "evidence_type": "code_files",
                    "files_to_sample": [
                        "app/TransactionRules/Actions/",
                        "app/TransactionRules/Triggers/",
                        "app/Engines/",
                        "app/Support/Search/",
                        "app/Models/Rule.php",
                        "app/Models/RuleAction.php"
                    ],
                    "sample_strategy": "stratified_dirs",
                    "max_files_per_dir": 5,
                    "max_total_files": 15,
                    "rubric_prompt": "Score 0-5 the TransactionRules engine design: (1) presence of a common Action contract/interface (e.g. ActionInterface) and 20+ concrete Action subclasses each handling a distinct action_type — 0..2pt (Strategy pattern); (2) Triggers similarly polymorphic with a shared contract — 0..1pt; (3) the engine that fires rules cleanly delegates to Action/Trigger objects (no giant switch on action_type) — 0..1pt; (4) action_type strings are an enum or a registry (no scattered string literals) — 0..1pt. Output JSON {\"score\":<0-5>,\"reasoning\":\"<<=400 chars>>\",\"evidence\":[...]}.",
                    "score_range": [
                        0,
                        5
                    ]
                }
            }
        ],
        "scoring": {
            "category": "ArchitectureQuality",
            "subcategory": "RuleEngineStrategy",
            "method": "llm-judge",
            "maxScore": 18
        },
        "complexity_tier": "workflow_automator",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-RULE-ACTIONS-31",
            "KB-ARCH-STRATEGY-RULES"
        ],
        "source_evidence": {
            "source_file": "Architecture §7.4",
            "behavior_verified": "Static / source-derived; subcategory=RuleEngineStrategy",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DEPLOY_HEALTH"
        ]
    }
    return execute_primitive_chain(node, context)


def test_ARCH_FACTORY_PATTERN(context: dict) -> NodeResult:
    node = {
        "id": "ARCH_FACTORY_PATTERN",
        "description": "LLM-judge: assess whether TransactionFactory + AccountFactory encapsulate the considerable complexity of creating valid double-entry transactions and accounts (validation, currency resolution, opening balance side effects). Sample app/Factory/.",
        "primitive_chain": [
            {
                "type": "P17",
                "inputs": {
                    "evidence_type": "code_files",
                    "files_to_sample": [
                        "app/Factory/",
                        "app/Factory/TransactionFactory.php",
                        "app/Factory/AccountFactory.php",
                        "app/Factory/TransactionGroupFactory.php",
                        "app/Factory/TransactionJournalFactory.php"
                    ],
                    "sample_strategy": "stratified_dirs",
                    "max_files_per_dir": 6,
                    "max_total_files": 10,
                    "rubric_prompt": "Score 0-5: (1) a Factory class exists for each compound aggregate (TransactionGroup, TransactionJournal, Transaction, Account, PiggyBank, Recurrence) — 0..2pt; (2) factories own validation + cross-entity wiring (currency lookup, opening-balance side journal, account creation cascades) instead of leaking it into controllers/repositories — 0..2pt; (3) factories return persisted aggregates (or throw a typed exception) — never half-hydrated objects — 0..1pt. Output JSON {\"score\":<0-5>,\"reasoning\":\"<<=400 chars>>\",\"evidence\":[...]}.",
                    "score_range": [
                        0,
                        5
                    ]
                }
            }
        ],
        "scoring": {
            "category": "ArchitectureQuality",
            "subcategory": "FactoryPattern",
            "method": "llm-judge",
            "maxScore": 18
        },
        "complexity_tier": "workflow_automator",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ARCH-FACTORY-PATTERN",
            "KB-021"
        ],
        "source_evidence": {
            "source_file": "Architecture §7.4",
            "behavior_verified": "Static / source-derived; subcategory=FactoryPattern",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DEPLOY_HEALTH"
        ]
    }
    return execute_primitive_chain(node, context)


def test_ARCH_CODE_SMELLS(context: dict) -> NodeResult:
    node = {
        "id": "ARCH_CODE_SMELLS",
        "description": "LLM-judge: sample 5 core Service files at random and look for code smells — God classes (>500 LOC, >25 public methods), long methods (>80 LOC), deep nesting (>4 levels), tight Eloquent coupling. A LOWER smell count yields a HIGHER score.",
        "primitive_chain": [
            {
                "type": "P17",
                "inputs": {
                    "evidence_type": "code_files",
                    "files_to_sample": [
                        "app/Services/",
                        "app/Support/",
                        "app/Repositories/Account/AccountRepository.php",
                        "app/Repositories/TransactionGroup/TransactionGroupRepository.php",
                        "app/Repositories/Budget/BudgetRepository.php"
                    ],
                    "sample_strategy": "random_n",
                    "n": 5,
                    "rubric_prompt": "For each of the 5 sampled files, count: (a) total LOC, (b) public method count, (c) longest method LOC, (d) max nesting depth, (e) direct ::create / ::where / ::find calls. Then score the WHOLE batch 0-5 where 5=very clean, 0=multiple God classes. Specifically: 5pt if all files <300 LOC AND no method >50 LOC AND nesting <=3; 4pt if at most one file mildly violates; 3pt baseline; 1-2pt if >=2 files are God classes (>500 LOC or >25 methods); 0pt if everything is bloated. Output JSON {\"score\":<0-5>,\"reasoning\":\"<<=400 chars>>\",\"per_file\":[{\"file\":\"...\",\"loc\":N,\"methods\":N,\"longest_method_loc\":N,\"max_nesting\":N}]}.",
                    "score_range": [
                        0,
                        5
                    ]
                }
            }
        ],
        "scoring": {
            "category": "ArchitectureQuality",
            "subcategory": "CodeSmells",
            "method": "llm-judge",
            "maxScore": 18
        },
        "complexity_tier": "workflow_automator",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-ARCH-CODE-SMELLS"
        ],
        "source_evidence": {
            "source_file": "Architecture §7.4",
            "behavior_verified": "Static / source-derived; subcategory=CodeSmells",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "DEPLOY_HEALTH"
        ]
    }
    return execute_primitive_chain(node, context)


def test_ARCH_FRONTEND_BLADE_PARTIALS(context: dict) -> NodeResult:
    node = {
        "id": "ARCH_FRONTEND_BLADE_PARTIALS",
        "description": "LLM-judge: assess Blade/Twig template reuse — does resources/views/ have a components/ or partials/ directory? Are common UI fragments (forms, tables, alerts) extracted? Sample resources/views/.",
        "primitive_chain": [
            {
                "type": "P17",
                "inputs": {
                    "evidence_type": "code_files",
                    "files_to_sample": [
                        "resources/views/",
                        "resources/views/layouts/",
                        "resources/views/components/",
                        "resources/views/partials/",
                        "resources/views/v1/",
                        "resources/views/v2/"
                    ],
                    "sample_strategy": "stratified_dirs",
                    "max_files_per_dir": 4,
                    "max_total_files": 16,
                    "rubric_prompt": "Score 0-5 the template reuse strategy: (1) a top-level layouts/ directory exists with at least one parent layout that child templates extend (@extends or {% extends %}) — 0..1pt; (2) common UI fragments (form rows, table headers, alerts, breadcrumbs) are extracted into components/ OR partials/ — 0..2pt; (3) child templates ACTUALLY use those partials (@include / {% include %} found across multiple subdirs) — 0..1pt; (4) no copy-pasted blocks of >30 identical lines across pages — 0..1pt. Output JSON {\"score\":<0-5>,\"reasoning\":\"<<=400 chars>>\",\"evidence\":[\"<<file>>\", ...]}.",
                    "score_range": [
                        0,
                        5
                    ]
                }
            }
        ],
        "scoring": {
            "category": "ArchitectureQuality",
            "subcategory": "BladePartials",
            "method": "llm-judge",
            "maxScore": 18
        },
        "complexity_tier": "workflow_automator",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-068",
            "KB-ARCH-BLADE-PARTIALS"
        ],
        "source_evidence": {
            "source_file": "Architecture §7.4",
            "behavior_verified": "Static / source-derived; subcategory=BladePartials",
            "needs_api_behavior_verification": False
        },
        "prereqs": [
            "FRONTEND_LAYOUT_BLADE_FILE_EXISTS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_ARCH_UI_DASHBOARD_LAYOUT_QUALITY(context: dict) -> NodeResult:
    _fetch_web_page_authenticated(context, "/")
    node = {
        "id": "ARCH_UI_DASHBOARD_LAYOUT_QUALITY",
        "description": "Dashboard page layout is clean, navigable, and presents key financial info without clutter (subjective UI judgment)",
        "primitive_chain": [
            {
                "type": "P17",
                "inputs": {
                    "evidence_type": "http_response_html",
                    "rubric_prompt": "Score the dashboard HTML on a 0-10 scale based on: (a) navigation clarity (sidebar/topbar present and labeled), (b) information density (key metrics visible without scrolling), (c) widget arrangement (account balances, recent transactions, budget progress visible), (d) accessibility (ARIA labels, semantic HTML).",
                    "score_range": [
                        0,
                        10
                    ]
                }
            }
        ],
        "scoring": {
            "category": "ArchitectureQuality",
            "subcategory": "DashboardUIQuality",
            "method": "llm-judge",
            "maxScore": 31
        },
        "complexity_tier": "linear_crud",
        "source_evidence": {
            "source_file": "Frontend §7",
            "behavior_verified": "Subjective HTML structure judgment"
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT",
            "DEPLOY_HEALTH"
        ]
    }
    return execute_primitive_chain(node, context)


def test_ARCH_UI_TRANSACTION_FORM_USABILITY(context: dict) -> NodeResult:
    _fetch_web_page_authenticated(context, "/transactions/create/withdrawal")
    node = {
        "id": "ARCH_UI_TRANSACTION_FORM_USABILITY",
        "description": "Transaction creation form is intuitive, with clear fields, helpful placeholders, and inline validation messages",
        "primitive_chain": [
            {
                "type": "P17",
                "inputs": {
                    "evidence_type": "http_response_html",
                    "rubric_prompt": "Evaluate the transaction creation form: (a) presence of source/destination/amount/date/description fields, (b) placeholder text or helper labels, (c) autocomplete dropdowns for accounts, (d) form action attribute, (e) inline validation hooks (Alpine.js / x-data attrs). 0-10.",
                    "score_range": [
                        0,
                        10
                    ]
                }
            }
        ],
        "scoring": {
            "category": "ArchitectureQuality",
            "subcategory": "TransactionFormUsability",
            "method": "llm-judge",
            "maxScore": 26
        },
        "complexity_tier": "linear_crud",
        "source_evidence": {
            "source_file": "Frontend §7",
            "behavior_verified": "Subjective form-quality judgment"
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_ARCH_UI_BUDGET_VISUALIZATION(context: dict) -> NodeResult:
    _fetch_web_page_authenticated(context, "/budgets")
    node = {
        "id": "ARCH_UI_BUDGET_VISUALIZATION",
        "description": "Budget overview page presents progress visually (progress bars, color-coded warnings, period boundaries)",
        "primitive_chain": [
            {
                "type": "P17",
                "inputs": {
                    "evidence_type": "http_response_html",
                    "rubric_prompt": "Evaluate the budgets page: (a) progress visualization (bars/charts), (b) over-budget red highlighting, (c) period selector, (d) per-budget drill-down link, (e) total spent vs total budget summary at top. 0-10.",
                    "score_range": [
                        0,
                        10
                    ]
                }
            }
        ],
        "scoring": {
            "category": "ArchitectureQuality",
            "subcategory": "BudgetVisualization",
            "method": "llm-judge",
            "maxScore": 22
        },
        "complexity_tier": "linear_crud",
        "source_evidence": {
            "source_file": "Frontend §7",
            "behavior_verified": "Subjective visualization-quality judgment"
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_ARCH_ERROR_MSG_VALIDATION_QUALITY(context: dict) -> NodeResult:
    node = {
        "id": "ARCH_ERROR_MSG_VALIDATION_QUALITY",
        "description": "422 validation errors include human-friendly, actionable messages (not just technical jargon)",
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
                    "path": "/api/v1/accounts",
                    "body": {}
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 422
                }
            },
            {
                "type": "P17",
                "inputs": {
                    "evidence_type": "http_response_json",
                    "rubric_prompt": "Evaluate the 422 error response: (a) presence of `errors` object keyed by field, (b) per-field arrays of human-readable messages, (c) overall `message` field with summary, (d) absence of stack traces / class names. 0-10.",
                    "score_range": [
                        0,
                        10
                    ]
                }
            }
        ],
        "scoring": {
            "category": "ArchitectureQuality",
            "subcategory": "ErrorMessageQuality",
            "method": "llm-judge",
            "maxScore": 18
        },
        "complexity_tier": "linear_crud",
        "source_evidence": {
            "source_file": "API §6.2.5",
            "behavior_verified": "Subjective error-message friendliness"
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_ARCH_ERROR_MSG_404_INFORMATIVE(context: dict) -> NodeResult:
    node = {
        "id": "ARCH_ERROR_MSG_404_INFORMATIVE",
        "description": "404 not-found responses convey which resource type was missing without leaking internals",
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
                    "path": "/api/v1/accounts/999999999"
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "expected_status": 404
                }
            },
            {
                "type": "P17",
                "inputs": {
                    "evidence_type": "http_response_json",
                    "rubric_prompt": "Score the 404 response: (a) `message` field present with resource-type hint, (b) no stack trace, no PHP class FQN beyond Models prefix, (c) consistent shape with other 404s. 0-10.",
                    "score_range": [
                        0,
                        10
                    ]
                }
            }
        ],
        "scoring": {
            "category": "ArchitectureQuality",
            "subcategory": "Error404Informativeness",
            "method": "llm-judge",
            "maxScore": 13
        },
        "complexity_tier": "linear_crud",
        "source_evidence": {
            "source_file": "API §6.2.5",
            "behavior_verified": "Subjective 404 message clarity"
        },
        "prereqs": [
            "AUTH_LOGIN_PASSWORD_GRANT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_ARCH_CODE_REPOSITORY_PATTERN_PRESENCE(context: dict) -> NodeResult:
    node = {
        "id": "ARCH_CODE_REPOSITORY_PATTERN_PRESENCE",
        "description": "Repository pattern is consistently applied: Controllers do not directly call Eloquent::query() (subjective code-quality judgment)",
        "primitive_chain": [
            {
                "type": "P17",
                "inputs": {
                    "evidence_type": "code_files",
                    "files_to_sample": [
                        "app/Http/Controllers",
                        "app/Repositories"
                    ],
                    "rubric_prompt": "Audit a sample of Controllers and Repositories: (a) Repositories present for each core entity, (b) Controllers inject Repository contracts via constructor, (c) raw Eloquent::query() calls in Controllers are absent, (d) clear interface/implementation split. 0-10.",
                    "score_range": [
                        0,
                        10
                    ]
                }
            }
        ],
        "scoring": {
            "category": "ArchitectureQuality",
            "subcategory": "RepositoryPattern",
            "method": "llm-judge",
            "maxScore": 26
        },
        "complexity_tier": "workflow_automator",
        "source_evidence": {
            "source_file": "Architecture §7.4",
            "behavior_verified": "Subjective code-organization quality"
        },
        "prereqs": [
            "DEPLOY_HEALTH"
        ]
    }
    return execute_primitive_chain(node, context)


def test_ARCH_CODE_FACTORY_PATTERN_USAGE(context: dict) -> NodeResult:
    node = {
        "id": "ARCH_CODE_FACTORY_PATTERN_USAGE",
        "description": "TransactionFactory + AccountFactory encapsulate complex entity creation logic",
        "primitive_chain": [
            {
                "type": "P17",
                "inputs": {
                    "evidence_type": "code_files",
                    "files_to_sample": [
                        "app/Factory"
                    ],
                    "rubric_prompt": "Evaluate Factory layer: (a) TransactionFactory and TransactionJournalFactory exist, (b) factories handle the source/destination Transaction sign convention, (c) AccountFactory handles opening_balance auto-creation, (d) factories return validated/persisted entities. 0-10.",
                    "score_range": [
                        0,
                        10
                    ]
                }
            }
        ],
        "scoring": {
            "category": "ArchitectureQuality",
            "subcategory": "FactoryPattern",
            "method": "llm-judge",
            "maxScore": 22
        },
        "complexity_tier": "workflow_automator",
        "source_evidence": {
            "source_file": "Architecture §7.4",
            "behavior_verified": "Subjective factory-layer quality"
        },
        "prereqs": [
            "DEPLOY_HEALTH"
        ]
    }
    return execute_primitive_chain(node, context)


def test_ARCH_RULE_ENGINE_STRATEGY_PATTERN(context: dict) -> NodeResult:
    node = {
        "id": "ARCH_RULE_ENGINE_STRATEGY_PATTERN",
        "description": "TransactionRules engine uses strategy pattern (interface + 31 action implementations) for extensibility",
        "primitive_chain": [
            {
                "type": "P17",
                "inputs": {
                    "evidence_type": "code_files",
                    "files_to_sample": [
                        "app/TransactionRules/Actions",
                        "app/TransactionRules/Engine"
                    ],
                    "rubric_prompt": "Evaluate Rule Engine architecture: (a) ActionInterface contract exists, (b) ~31 action implementations follow the contract, (c) SearchRuleEngine uses query parser instead of Eloquent for trigger matching, (d) ActionExpression integrates Symfony ExpressionLanguage. 0-10.",
                    "score_range": [
                        0,
                        10
                    ]
                }
            }
        ],
        "scoring": {
            "category": "ArchitectureQuality",
            "subcategory": "RuleEngineStrategyPattern",
            "method": "llm-judge",
            "maxScore": 26
        },
        "complexity_tier": "workflow_automator",
        "source_evidence": {
            "source_file": "Business Logic §5",
            "behavior_verified": "Subjective architecture-pattern judgment"
        },
        "prereqs": [
            "DEPLOY_HEALTH"
        ]
    }
    return execute_primitive_chain(node, context)


def test_ARCH_I18N_COVERAGE_QUALITY(context: dict) -> NodeResult:
    node = {
        "id": "ARCH_I18N_COVERAGE_QUALITY",
        "description": "Default UI strings are externalized into resources/lang/en_US/* (no hardcoded English in templates)",
        "primitive_chain": [
            {
                "type": "P17",
                "inputs": {
                    "evidence_type": "code_files",
                    "files_to_sample": [
                        "resources/views",
                        "resources/lang/en_US"
                    ],
                    "rubric_prompt": "Evaluate i18n quality: (a) Blade templates use `__()` / `trans()` helpers instead of inline strings, (b) lang/en_US/ contains pfm.php / form.php / validation.php, (c) at least one non-English locale present, (d) date/number formatting respects locale. 0-10.",
                    "score_range": [
                        0,
                        10
                    ]
                }
            }
        ],
        "scoring": {
            "category": "ArchitectureQuality",
            "subcategory": "I18nCoverage",
            "method": "llm-judge",
            "maxScore": 18
        },
        "complexity_tier": "linear_crud",
        "source_evidence": {
            "source_file": "Frontend §7.5",
            "behavior_verified": "Subjective i18n-coverage quality"
        },
        "prereqs": [
            "DEPLOY_HEALTH"
        ]
    }
    return execute_primitive_chain(node, context)


def test_ARCH_API_DOC_QUALITY(context: dict) -> NodeResult:
    node = {
        "id": "ARCH_API_DOC_QUALITY",
        "description": "API documentation (README / OpenAPI / inline PHP docblocks) is sufficient for a third-party developer to integrate",
        "primitive_chain": [
            {
                "type": "P17",
                "inputs": {
                    "evidence_type": "code_files",
                    "files_to_sample": [
                        "README.md",
                        "docs/",
                        "app/Api/V1"
                    ],
                    "rubric_prompt": "Evaluate API documentation: (a) README mentions OAuth2 + token usage, (b) Controller methods carry PHPDoc with @param/@return, (c) FormRequest classes document validation rules, (d) error response shape documented. 0-10.",
                    "score_range": [
                        0,
                        10
                    ]
                }
            }
        ],
        "scoring": {
            "category": "ArchitectureQuality",
            "subcategory": "APIDocumentationQuality",
            "method": "llm-judge",
            "maxScore": 18
        },
        "complexity_tier": "linear_crud",
        "source_evidence": {
            "source_file": "API §6.1",
            "behavior_verified": "Subjective documentation completeness"
        },
        "prereqs": [
            "DEPLOY_HEALTH"
        ]
    }
    return execute_primitive_chain(node, context)

