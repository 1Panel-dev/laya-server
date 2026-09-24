#!/bin/sh
set -eu
expected=1e28ac20c0896b1c37a744cd11f740eb98f8b178
if [ ! -e laya/.git ]; then
  echo 'Missing ignored laya/ checkout' >&2
  exit 1
fi
actual=$(git -C laya rev-parse HEAD)
if [ "$actual" != "$expected" ] || [ -n "$(git -C laya status --porcelain)" ]; then
  echo "Laya checkout must be clean at $expected; found $actual" >&2
  exit 1
fi
echo "Laya checkout verified: $actual"
