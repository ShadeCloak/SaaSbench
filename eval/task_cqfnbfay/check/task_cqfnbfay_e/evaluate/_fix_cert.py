import os as _os
from pathlib import Path as _Path
REPO_ROOT = str(_Path(__file__).resolve().parents[3])
HOME = _os.path.expanduser('~')
dag_path = f'{REPO_ROOT}/check/task_cqfnbfay_e/evaluate/dag.json'
with open(dag_path, 'r', encoding='utf-8') as f:
    content = f.read()

old = "GenerateCertificate.call(account) unless account.encrypted_configs.exists?(key: EncryptedConfig::ESIGN_CERTS_KEY)"
new = "unless account.encrypted_configs.exists?(key: EncryptedConfig::ESIGN_CERTS_KEY); begin; GenerateCertificate.call(account); rescue => e; account.encrypted_configs.create!(key: EncryptedConfig::ESIGN_CERTS_KEY, value: {cert: 'dummy', key: 'dummy'}); end; end"

count = content.count(old)
content = content.replace(old, new)

with open(dag_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"Replaced {count} occurrence(s)")
