#!/bin/sh
set -eu
expected=9d955671415fc19f069b9cc998928075c1f255ec
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
