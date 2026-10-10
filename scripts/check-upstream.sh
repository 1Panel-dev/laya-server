#!/bin/sh
set -eu
expected=68804629e8ccd9d616d48a40e87de9fabbeae069
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
