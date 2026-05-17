#!/bin/bash
# NeuralMemory Installer
# Usage:
#   ./install.sh              # Interactive
#   ./install.sh --auto       # Non-interactive
#   ./install.sh --clean      # Remove hook and skill

set -e

SKILLS_DIR="${HERMES_HOME:-$HOME/.hermes}/skills"
SKILL_DIR="$SKILLS_DIR/neural-memory"
CONFIG_YAML="$HOME/.hermes/config.yaml"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ---- Uninstall ----
do_uninstall() {
    info "Uninstalling NeuralMemory..."

    # Remove hook from config.yaml
    if [ -f "$CONFIG_YAML" ]; then
        python3 -c "
import yaml, sys
with open('$CONFIG_YAML') as f:
    config = yaml.safe_load(f) or {}
hook_script = '$(pwd)/hooks/capture.py'
if 'hooks' in config and 'post_tool_call' in config['hooks']:
    config['hooks']['post_tool_call'] = [
        h for h in config['hooks']['post_tool_call']
        if not (isinstance(h, dict) and hook_script in h.get('command', ''))
    ]
    if not config['hooks']['post_tool_call']:
        del config['hooks']['post_tool_call']
if 'mcp' in config and 'servers' in config.get('mcp', {}):
    config['mcp']['servers'].pop('neural-memory', None)
with open('$CONFIG_YAML', 'w') as f:
    yaml.dump(config, f, default_flow_style=False, sort_keys=False)
print('Hook removed from config.yaml')
"
    fi

    # Remove skill directory
    if [ -d "$SKILL_DIR" ]; then
        rm -rf "$SKILL_DIR"
        info "Skill directory removed: $SKILL_DIR"
    fi

    info "Uninstall complete"
}

# ---- Install ----
do_install() {
    local auto="$1"

    info "NeuralMemory Installer"
    echo

    # Step 1: Install dependencies
    if [ "$auto" = "interactive" ]; then
        read -rp "Install Python dependencies? [Y/n] " ans
        if [ "$ans" = "n" ]; then
            warn "Skipping dependencies"
        else
            info "Installing dependencies..."
            pip install --quiet streamlit>=1.30.0 sentence-transformers>=2.2.0 rank-bm25>=0.2.0 pyyaml>=6.0
            info "Dependencies installed"
        fi
    else
        info "Installing dependencies..."
        pip install --quiet streamlit>=1.30.0 sentence-transformers>=2.2.0 rank-bm25>=0.2.0 pyyaml>=6.0
        info "Dependencies installed"
    fi

    # Step 2: Configure hook
    if [ "$auto" = "interactive" ]; then
        read -rp "Configure PostToolUse hook? [Y/n] " ans
        if [ "$ans" = "n" ]; then
            warn "Skipping hook"
        else
            info "Configuring PostToolUse hook..."
            python3 setup.py --hook
        fi
    else
        info "Configuring PostToolUse hook..."
        python3 setup.py --hook
    fi

    # Step 3: Configure MCP
    if [ "$auto" = "interactive" ]; then
        read -rp "Configure MCP server? [Y/n] " ans
        if [ "$ans" = "n" ]; then
            warn "Skipping MCP server"
        else
            info "Configuring MCP server..."
            python3 setup.py --mcp
        fi
    else
        info "Configuring MCP server..."
        python3 setup.py --mcp
    fi

    # Step 4: Create skill
    info "Installing skill..."
    python3 setup.py 2>/dev/null || true  # create_skill is part of auto_setup
    # Actually call create_skill directly
    python3 -c "
import sys, shutil
from pathlib import Path
sys.path.insert(0, '.')
from setup import PROJECT_ROOT, SKILLS_DIR
skill_dir = SKILLS_DIR / 'neural-memory'
if skill_dir.exists():
    shutil.rmtree(skill_dir)
shutil.copytree(PROJECT_ROOT, skill_dir, ignore=shutil.ignore_patterns(
    '__pycache__', '.pytest_cache', '*.pyc', '.git', '~', '*.db', '*.json'
))
print(f'Skill installed at {skill_dir}')
"

    echo
    info "Installation complete!"
    echo
    info "Next steps:"
    echo "  1. Restart Hermes for hook to take effect"
    echo "  2. Start GUI: streamlit run src/dashboard/app.py"
    echo "  3. Or use via MCP server (auto-configured)"
    echo
    info "Debug: set NEURAL_MEMORY_DEBUG=1 to log all events to stderr"
}

# ---- Main ----
case "${1:-}" in
    --clean)
        do_uninstall
        ;;
    --auto)
        do_install "auto"
        ;;
    "")
        do_install "interactive"
        ;;
    *)
        error "Unknown option: $1"
        echo "Usage: $0 [--auto | --clean]"
        exit 1
        ;;
esac
