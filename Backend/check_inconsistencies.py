import re
from pathlib import Path

js_files = list(Path('app/templates').rglob('*.html')) + list(Path('app/static').rglob('*.js'))

api_calls = []
pattern = re.compile(r"api\.(post|put|delete)\s*\(\s*['\"`]+([^'\"`]+)['\"`]+(?:\s*,\s*({[\s\S]*?}|[^)]+))?\s*\)")

for f in js_files:
    content = f.read_text(encoding='utf-8')
    for m in pattern.finditer(content):
        method, url, payload = m.groups()
        if payload:
            payload = payload.strip()
        api_calls.append((f.name, method, url, payload))

for call in api_calls:
    print(f"{call[0]} | {call[1].upper()} {call[2]} | {call[3]}")
