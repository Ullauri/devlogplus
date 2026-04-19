#!/usr/bin/env bash
# Pre-commit hook helper: regenerate OpenAPI spec + TS types, but only
# stage (and therefore signal to pre-commit) when content actually
# changes. This avoids a "files were modified by this hook"
# false-positive when the regenerated output is byte-identical to
# what is already staged.
set -euo pipefail

spec=docs/openapi.json
types=frontend/src/api/schema.gen.ts

cp "$spec" "$spec.bak"
cp "$types" "$types.bak"

make openapi >/dev/null

changed=0
cmp -s "$spec" "$spec.bak" || changed=1
cmp -s "$types" "$types.bak" || changed=1

if [ "$changed" -eq 0 ]; then
  # Byte-identical: restore originals so pre-commit sees no change.
  mv "$spec.bak" "$spec"
  mv "$types.bak" "$types"
else
  rm -f "$spec.bak" "$types.bak"
  git add "$spec" "$types"
fi
