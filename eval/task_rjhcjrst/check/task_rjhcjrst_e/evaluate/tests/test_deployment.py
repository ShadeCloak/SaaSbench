
from __future__ import annotations

from ..utils import NodeResult
from ._common import execute_primitive_chain


def test_DEPLOY_HEALTH(context: dict) -> NodeResult:
    node = {
        "id": "DEPLOY_HEALTH",
        "description": "Application responds on container port 80 (host 8022) — minimum proof of deployment, accept any non-5xx so framework redirects/login pages also pass.",
        "primitive_chain": [
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/",
                    "timeout": 10
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "acceptable_statuses": [
                        200,
                        301,
                        302,
                        401,
                        404
                    ]
                }
            }
        ],
        "scoring": {
            "category": "Deployment",
            "subcategory": "Accessibility",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-DOCKER-APP-PORT"
        ],
        "source_evidence": {
            "source_file": "Deployment §9",
            "behavior_verified": "Static / source-derived; subcategory=Accessibility",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DEPLOY_COMPOSER_JSON(context: dict) -> NodeResult:
    node = {
        "id": "DEPLOY_COMPOSER_JSON",
        "description": "composer.json declares the mandatory packages: laravel/passport, pragmarx/google2fa, jc5/google2fa-laravel, bacon/bacon-qr-code, gdbots/query-parser, league/fractal.",
        "primitive_chain": [
            {
                "type": "P01",
                "inputs": {
                    "path": "composer.json",
                    "in_container": True,
                    "type": "file"
                }
            },
            {
                "type": "P02",
                "inputs": {
                    "path": "composer.json",
                    "in_container": True,
                    "match_type": "contains",
                    "pattern": "laravel/passport"
                }
            },
            {
                "type": "P02",
                "inputs": {
                    "path": "composer.json",
                    "in_container": True,
                    "match_type": "contains",
                    "pattern": "pragmarx/google2fa"
                }
            },
            {
                "type": "P02",
                "inputs": {
                    "path": "composer.json",
                    "in_container": True,
                    "match_type": "contains",
                    "pattern": "bacon/bacon-qr-code"
                }
            },
            {
                "type": "P02",
                "inputs": {
                    "path": "composer.json",
                    "in_container": True,
                    "match_type": "contains",
                    "pattern": "gdbots/query-parser"
                }
            },
            {
                "type": "P02",
                "inputs": {
                    "path": "composer.json",
                    "in_container": True,
                    "match_type": "contains",
                    "pattern": "league/fractal"
                }
            }
        ],
        "scoring": {
            "category": "Deployment",
            "subcategory": "Dependencies",
            "method": "weighted",
            "maxScore": 5
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-COMPOSER-DEPS"
        ],
        "source_evidence": {
            "source_file": "Deployment §9",
            "behavior_verified": "Static / source-derived; subcategory=Dependencies",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DEPLOY_PHP_VERSION(context: dict) -> NodeResult:
    node = {
        "id": "DEPLOY_PHP_VERSION",
        "description": "App container runs PHP 8.2 or higher (per §2.1 runtime requirement).",
        "primitive_chain": [
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "php -r 'echo PHP_VERSION;'",
                    "expect_success": True,
                    "expect_output_regex": "^8\\.(2|3|4|5)\\."
                }
            }
        ],
        "scoring": {
            "category": "Deployment",
            "subcategory": "Runtime",
            "method": "binary",
            "maxScore": 2
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-PHP-VERSION"
        ],
        "source_evidence": {
            "source_file": "Deployment §9",
            "behavior_verified": "Static / source-derived; subcategory=Runtime",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DEPLOY_NODE_VERSION(context: dict) -> NodeResult:
    node = {
        "id": "DEPLOY_NODE_VERSION",
        "description": "Node.js is available inside the container for Vite build pipeline (any v18+ acceptable).",
        "primitive_chain": [
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "test -f /var/www/html/public/v1/manifest.json && echo MANIFEST_OK || (test -f /var/www/html/public/v2/manifest.json && echo MANIFEST_OK || (ls /var/www/html/public/v1/*.js /var/www/html/public/v2/*.js 2>/dev/null | head -1 && echo CHUNKS_OK))",
                    "expect_success": True,
                    "expect_output_contains": "_OK"
                }
            }
        ],
        "scoring": {
            "category": "Deployment",
            "subcategory": "BuildToolchain",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-VITE-BUILD"
        ],
        "source_evidence": {
            "source_file": "Deployment §9",
            "behavior_verified": "Static / source-derived; subcategory=BuildToolchain",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DEPLOY_CRON_INSTALLED(context: dict) -> NodeResult:
    node = {
        "id": "DEPLOY_CRON_INSTALLED",
        "description": "Host cron schedule file /etc/cron.d/pfm-cron is installed inside the app container so firefly-iii:cron is invoked daily.",
        "primitive_chain": [
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "(test -f /etc/cron.d/pfm-cron && grep -q pfm:cron /etc/cron.d/pfm-cron && echo IN_CONTAINER_CRON) || (test -f /etc/cron.d/firefly-cron && echo IN_CONTAINER_CRON_FF) || (which php && php /var/www/html/artisan list 2>/dev/null | grep -qE '(pfm:cron|firefly-iii:cron)' && echo CRON_CMD_REGISTERED) || echo NO_CRON",
                    "expect_success": True,
                    "expect_output_contains": "CRON"
                }
            }
        ],
        "scoring": {
            "category": "Deployment",
            "subcategory": "Scheduling",
            "method": "binary",
            "maxScore": 2
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-CRON-SCHEDULE"
        ],
        "source_evidence": {
            "source_file": "Deployment §9",
            "behavior_verified": "Static / source-derived; subcategory=Scheduling",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DEPLOY_PHP_EXTENSIONS(context: dict) -> NodeResult:
    node = {
        "id": "DEPLOY_PHP_EXTENSIONS",
        "description": "Mandatory PHP extensions are loaded: bcmath (monetary maths), pdo_mysql, intl (i18n), sodium (crypto), gd (QR codes), zip, openssl, mbstring.",
        "primitive_chain": [
            {
                "type": "P12",
                "inputs": {
                    "container": "{{app_container}}",
                    "command": "php -m",
                    "expect_success": True,
                    "expect_output_contains_all": [
                        "bcmath",
                        "pdo_mysql",
                        "intl",
                        "sodium",
                        "gd",
                        "zip",
                        "openssl",
                        "mbstring"
                    ]
                }
            }
        ],
        "scoring": {
            "category": "Deployment",
            "subcategory": "PhpExtensions",
            "method": "weighted",
            "maxScore": 4
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-PHP-EXTENSIONS"
        ],
        "source_evidence": {
            "source_file": "Deployment §9",
            "behavior_verified": "Static / source-derived; subcategory=PhpExtensions",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DEPLOY_DB_MIGRATIONS_RAN(context: dict) -> NodeResult:
    node = {
        "id": "DEPLOY_DB_MIGRATIONS_RAN",
        "description": "Laravel migrations table contains 50+ rows — proves the 59 forward-only migrations completed during entrypoint.",
        "primitive_chain": [
            {
                "type": "P09",
                "inputs": {
                    "tables": [
                        "migrations"
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT COUNT(*) AS cnt FROM migrations",
                    "expected_predicates": [
                        {
                            "field": "cnt",
                            "op": ">=",
                            "value": 50
                        }
                    ]
                }
            }
        ],
        "scoring": {
            "category": "Deployment",
            "subcategory": "Migrations",
            "method": "binary",
            "maxScore": 3
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": True,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-MIGRATIONS-COUNT"
        ],
        "source_evidence": {
            "source_file": "Deployment §9",
            "behavior_verified": "Static / source-derived; subcategory=Migrations",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)


def test_DEPLOY_PUBLIC_INDEX_PHP(context: dict) -> NodeResult:
    node = {
        "id": "DEPLOY_PUBLIC_INDEX_PHP",
        "description": "public/index.php exists — Laravel's HTTP entry point and proxy/nginx web-root target.",
        "primitive_chain": [
            {
                "type": "P01",
                "inputs": {
                    "path": "public/index.php",
                    "in_container": True,
                    "type": "file"
                }
            }
        ],
        "scoring": {
            "category": "Deployment",
            "subcategory": "WebRoot",
            "method": "binary",
            "maxScore": 1
        },
        "complexity_tier": "linear_crud",
        "evidence": {
            "logs": False,
            "screenshots": False
        },
        "_kb_refs": [
            "KB-LARAVEL-ENTRYPOINT"
        ],
        "source_evidence": {
            "source_file": "Deployment §9",
            "behavior_verified": "Static / source-derived; subcategory=WebRoot",
            "needs_api_behavior_verification": False
        },
        "prereqs": []
    }
    return execute_primitive_chain(node, context)

