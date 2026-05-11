#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="$HOME/.config/ollama-bridge"

echo "Installing OllamaBridge from $INSTALL_DIR"

if python3 -c "import aiohttp, httpx, yaml" 2>/dev/null; then
    echo "  [OK] Python deps (already installed system-wide)"
else
    VENV="$INSTALL_DIR/.venv"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install -r "$INSTALL_DIR/requirements.txt" --quiet
    PYTHON3="$VENV/bin/python3"
    echo "  [OK] Python deps (venv at $VENV)"
fi
PYTHON3="${PYTHON3:-python3}"

mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    cp "$INSTALL_DIR/config.yaml.example" "$CONFIG_DIR/config.yaml"
    echo "  [OK] Config created at $CONFIG_DIR/config.yaml"
else
    echo "  [SKIP] Config already exists"
fi

mkdir -p "$CONFIG_DIR/hooks"
cp "$INSTALL_DIR/hooks/usage_inject.sh" "$CONFIG_DIR/hooks/"
chmod +x "$CONFIG_DIR/hooks/usage_inject.sh"
echo "  [OK] Hook installed"

SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_DIR"
sed -e "s|/path/to/ollama-bridge|$INSTALL_DIR|g" \
    -e "s|/path/to/python3|$(which "$PYTHON3")|g" \
    "$INSTALL_DIR/ollama-bridge.service" > "$SYSTEMD_DIR/ollama-bridge.service"
systemctl --user daemon-reload
systemctl --user enable ollama-bridge
systemctl --user start ollama-bridge
echo "  [OK] systemd service started"

"$PYTHON3" "$INSTALL_DIR/scripts/patch_claude_settings.py"
echo "  [OK] ~/.claude/settings.json patched"

echo ""
echo "REQUIRED:"
echo "  echo 'ANTHROPIC_API_KEY=sk-ant-...' > $CONFIG_DIR/env && chmod 600 $CONFIG_DIR/env"
echo "  Set OLLAMA_API_KEY in $CONFIG_DIR/env if using Ollama Cloud"
echo "  Edit $CONFIG_DIR/config.yaml if plan limits differ"
echo ""
echo "Verify: python3 $INSTALL_DIR/cli.py status"
