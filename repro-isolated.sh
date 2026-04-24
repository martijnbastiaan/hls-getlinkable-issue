#!/usr/bin/env bash
# The error sometimes sticks around when minimizing the error. To work around this
# we copy the whole directory to a temporary directory and run the reproducer there.
TMP=$(mktemp -d)

cp -ap . "${TMP}"
cd "${TMP}"

git clean -fdx
nix develop --command ./repro.py

rm -rf "${TMP}"
