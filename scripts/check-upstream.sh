#!/bin/sh
set -eu
expected=010bacef009c855ccba814b51f7c8e1d38ab5e3f
if [ ! -d laya/.git ]; then
  echo 'Missing ignored laya/ checkout' >&2
  exit 1
fi
actual=$(git -C laya rev-parse HEAD)
if [ "$actual" != "$expected" ] || [ -n "$(git -C laya status --porcelain)" ]; then
  echo "Laya checkout must be clean at $expected; found $actual" >&2
  exit 1
fi
echo "Laya checkout verified: $actual"
