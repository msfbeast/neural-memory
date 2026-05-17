#!/usr/bin/env python3
"""NeuralMemory setup script — install and configure everything in one go.

Usage:
    python setup.py                  # Interactive setup
    python setup.py --auto           # Non-interactive, use defaults
    python setup.py --gui            # Start Streamlit GUI only
    python setup.py --hook           # Configure PostToolUse hook only
    python setup.py --mcp            # Configure MCP server only
    python setup.py --uninstall      # Remove hook and clean up
"""

import os
import sys
import json
import subprocess
import shutil
from pathlib import Path
from typing import Optional

# Paths
HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
NEURAL_MEMORY_DIR = Path(os.environ.get(
    "NEURAL_MEMORY_DIR",
    str(Path.home() / ".plur" / "neural_memory")
))
CONFIG_YAML = HERMES_HOME / "config.yaml"
SKILLS_DIR = HERMES_HOME / "skills"

# NeuralMemory project root
PROJECT_ROOT = Path(__file__).parent


def ensure_dirs():
    """Create required directories."""
    directories = [
        NEURAL_MEMORY_DIR,
    ]
    for d in directories:
        d.mkdir(parents=True, exist_ok=True)


def install_dependencies():
    """Install Python dependencies."""
    print("Installing dependencies...")

    deps = [
        "streamlit>=1.30.0",
        "sentence-transformers>=2.2.0",
        "rank-bm25>=0.2.0",
        "pyyaml>=6.0",
    ]

    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "--quiet", *deps
        ])
        print("Dependencies installed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        return False


def configure_hook():
    """Configure PostToolUse hook in config.yaml.

    Adds the hook to the existing hooks block without overwriting other hooks.
    """
    print("Configuring PostToolUse hook...")

    hook_script = str(PROJECT_ROOT / "hooks" / "capture.py")

    # Read existing config
    config = {}
    if CONFIG_YAML.exists():
        try:
            import yaml
            with open(CONFIG_YAML) as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            pass

    # Add hooks section
    if "hooks" not in config:
        config["hooks"] = {}

    # Add to post_tool_call (append if list exists)
    if "post_tool_call" not in config["hooks"]:
        config["hooks"]["post_tool_call"] = []

    # Check if our hook is already registered
    hook_entry = {"command": f"python3 {hook_script}"}
    existing_commands = [
        h.get("command", "") if isinstance(h, dict) else ""
        for h in config["hooks"]["post_tool_call"]
    ]
    if hook_script not in existing_commands:
        config["hooks"]["post_tool_call"].append({
            "command": f"python3 {hook_script}",
            "timeout": 5,
        })

    # Add capture config
    if "capture" not in config:
        config["capture"] = {}

    config["capture"]["enabled"] = True
    config["capture"]["max_events_per_session"] = 100
    config["capture"]["filter_patterns"] = [
        "user_correction",
        "debug_breakthrough",
        "tool_discovery",
        "user_preference",
        "budget_constraint",
        "file_operation",
        "config_change",
        "workflow_discovery",
    ]

    # Write config
    try:
        import yaml
        with open(CONFIG_YAML, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        print("PostToolUse hook configured in config.yaml")
        print(f"  Hook script: {hook_script}")
        return True
    except Exception as e:
        print(f"Failed to configure hook: {e}")
        return False


def configure_mcp_server():
    """Configure NeuralMemory as an MCP server in Hermes config."""
    print("Configuring MCP server...")

    mcp_server_entry = {
        "command": sys.executable,
        "args": [str(PROJECT_ROOT / "src" / "mcp" / "run.py")],
        "env": {
            "NEURAL_MEMORY_DIR": str(NEURAL_MEMORY_DIR),
        },
    }

    # Read existing config
    config = {}
    if CONFIG_YAML.exists():
        try:
            import yaml
            with open(CONFIG_YAML) as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            pass

    # Merge MCP config
    if "mcp" not in config:
        config["mcp"] = {}
    if "servers" not in config["mcp"]:
        config["mcp"]["servers"] = {}

    config["mcp"]["servers"]["neural-memory"] = mcp_server_entry

    # Write config
    try:
        import yaml
        with open(CONFIG_YAML, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        print("MCP server configured in config.yaml")
        return True
    except Exception as e:
        print(f"Failed to configure MCP server: {e}")
        return False


def create_skill():
    """Copy NeuralMemory into ~/.hermes/skills/neural-memory."""
    print("Installing skill...")

    skill_dir = SKILLS_DIR / "neural-memory"

    # Remove old install if exists
    if skill_dir.exists():
        shutil.rmtree(skill_dir)

    # Copy entire project
    shutil.copytree(PROJECT_ROOT, skill_dir, ignore=shutil.ignore_patterns(
        "__pycache__", ".pytest_cache", "*.pyc", ".git",
        "~", "*.db", "*.json",
    ))

    print(f"Skill installed at {skill_dir}")
    return True


def start_gui():
    """Start the Streamlit GUI."""
    print("Starting NeuralMemory GUI...")

    dashboard_path = PROJECT_ROOT / "src" / "dashboard" / "app.py"

    if not dashboard_path.exists():
        print("Dashboard not found")
        return False

    try:
        subprocess.Popen([
            sys.executable, "-m", "streamlit", "run",
            str(dashboard_path),
            "--server.port", "8507",
            "--server.headless", "true",
        ])
        print("GUI started at http://localhost:8507")
        return True
    except Exception as e:
        print(f"Failed to start GUI: {e}")
        return False


def uninstall():
    """Remove hook from config.yaml and skill directory."""
    print("Uninstalling NeuralMemory...")

    hook_script = str(PROJECT_ROOT / "hooks" / "capture.py")

    # Remove hook from config
    if CONFIG_YAML.exists():
        try:
            import yaml
            with open(CONFIG_YAML) as f:
                config = yaml.safe_load(f) or {}

            removed = False
            if "hooks" in config and "post_tool_call" in config["hooks"]:
                config["hooks"]["post_tool_call"] = [
                    h for h in config["hooks"]["post_tool_call"]
                    if isinstance(h, dict) and hook_script not in h.get("command", "")
                ]
                if not config["hooks"]["post_tool_call"]:
                    del config["hooks"]["post_tool_call"]
                removed = True

            if "mcp" in config and "servers" in config.get("mcp", {}):
                config["mcp"]["servers"].pop("neural-memory", None)
                removed = True

            if removed:
                with open(CONFIG_YAML, "w") as f:
                    yaml.dump(config, f, default_flow_style=False, sort_keys=False)
                print("Hook removed from config.yaml")
        except Exception as e:
            print(f"Failed to remove hook from config: {e}")

    # Remove skill directory
    skill_dir = SKILLS_DIR / "neural-memory"
    if skill_dir.exists():
        shutil.rmtree(skill_dir)
        print(f"Skill directory removed: {skill_dir}")

    print("Uninstall complete")


def main():
    """Main setup function."""
    args = sys.argv[1:]

    auto = "--auto" in args
    gui = "--gui" in args
    hook = "--hook" in args
    mcp = "--mcp" in args
    uninstall_flag = "--uninstall" in args

    if uninstall_flag:
        uninstall()
        return

    if not any([auto, gui, hook, mcp]):
        print("NeuralMemory Setup")
        print("=" * 40)
        print()
        print("Options:")
        print("  --auto      Non-interactive setup (install deps + configure)")
        print("  --gui       Start Streamlit GUI only")
        print("  --hook      Configure PostToolUse hook only")
        print("  --mcp       Configure MCP server only")
        print("  --uninstall Remove hook and clean up")
        print()
        interactive_setup()
    elif gui:
        start_gui()
    elif hook:
        configure_hook()
    elif mcp:
        configure_mcp_server()
    elif auto:
        auto_setup()
    else:
        interactive_setup()


def auto_setup():
    """Non-interactive setup."""
    print("NeuralMemory Auto Setup")
    print("=" * 40)
    print()

    ensure_dirs()
    install_dependencies()
    configure_hook()
    configure_mcp_server()
    create_skill()

    print()
    print("Setup complete!")
    print()
    print("Next steps:")
    print("  1. Restart Hermes for hook to take effect")
    print("  2. Start GUI: streamlit run src/dashboard/app.py")
    print("  3. Or use via MCP server (auto-configured)")
    print()
    print("Debug: set NEURAL_MEMORY_DEBUG=1 to log all events to stderr")


def interactive_setup():
    """Interactive setup."""
    print("NeuralMemory Setup")
    print("=" * 40)
    print()

    # Step 1: Install dependencies
    install_deps = input("Install dependencies? [Y/n] ").strip().lower()
    if install_deps != "n":
        install_dependencies()

    # Step 2: Configure hook
    config_hook = input("Configure PostToolUse hook? [Y/n] ").strip().lower()
    if config_hook != "n":
        configure_hook()

    # Step 3: Configure MCP
    config_mcp = input("Configure MCP server? [Y/n] ").strip().lower()
    if config_mcp != "n":
        configure_mcp_server()

    # Step 4: Create skill
    create_skill()

    # Step 5: Start GUI
    start_gui_inst = input("Start GUI now? [y/N] ").strip().lower()
    if start_gui_inst == "y":
        start_gui()

    print()
    print("Setup complete!")
    print()
    print("Next steps:")
    print("  1. Restart Hermes for hook to take effect")
    print("  2. Access GUI at http://localhost:8507")
    print("  3. Or use via MCP server")
    print()
    print("Debug: set NEURAL_MEMORY_DEBUG=1 to log all events to stderr")


if __name__ == "__main__":
    main()
