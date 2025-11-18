#!/usr/bin/env bash
set -euo pipefail

echo "[CI] Installing containerlab..."
curl -sL https://get.containerlab.dev | sudo bash

echo "[CI] containerlab version:"
sudo containerlab version

