_SAAS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # repo root

# LLM judge configuration (override via environment).
export LLM_API_BASE="${LLM_API_BASE:-https://api.commonstack.ai/v1}"
export LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}"
export LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}"

export UPSTREAM_BASE_URL="${UPSTREAM_BASE_URL:-https://YOUR_LLM_API_HOST/v1}"
export UPSTREAM_API_KEY="$LLM_API_KEY"

export PROXY_PORT=4000
export SAASBENCH_ANTHROPIC_BASE_URL_PORT=$PROXY_PORT

export SAASBENCH_CLAUDE_IDLE_KILL_SECONDS=1800

export AGENT_MODEL="claude-opus-4-7"
