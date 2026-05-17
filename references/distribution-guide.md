# NeuralMemory — Community Distribution Guide

This guide explains how to distribute NeuralMemory as a community package and how users can install and use it.

## Distribution Options

### Option 1: GitHub Repository (Recommended)

The easiest way to distribute NeuralMemory is via GitHub:

```bash
# Initialize a git repo (if not already done)
cd ~/.hermes/skills/neural-memory
git init
git add .
git commit -m "Initial NeuralMemory release"

# Create a GitHub repo and push
git remote add origin https://github.com/yourusername/neural-memory.git
git push -u origin main
```

Users can then install via:

```bash
# Method 1: Clone directly
git clone https://github.com/yourusername/neural-memory.git ~/.hermes/skills/neural-memory
cd ~/.hermes/skills/neural-memory
python setup.py --auto

# Method 2: Hermes skill tap
hermes skills tap add https://github.com/yourusername/neural-memory
```

### Option 2: Skill Hub

Publish to the Hermes skill hub:

```bash
# Publish to hub
hermes skills publish ~/.hermes/skills/neural-memory

# Or submit a PR to the skill hub
```

### Option 3: Pip Package

Create a pip-installable package:

```bash
# Create package structure
mkdir -p neural_memory
cp -r src neural_memory/
cp hooks neural_memory/
cp dashboard.py neural_memory/
cp mcp_server.py neural_memory/
cp setup.py neural_memory/

# Create pyproject.toml
cat > neural_memory/pyproject.toml << 'EOF'
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "neural-memory"
version = "1.0.0"
description = "Persistent agent memory for Hermes Agent"
requires-python = ">=3.9"
dependencies = [
    "streamlit>=1.30.0",
    "sentence-transformers>=2.2.0",
    "rank-bm25>=0.2.0",
    "pyyaml>=6.0",
    "rich>=13.0.0",
]

[project.scripts]
neural-memory-setup = "neural_memory.setup:main"
neural-memory-dashboard = "neural_memory.dashboard:main"
neural-memory-mcp = "neural_memory.mcp_server:main"
EOF

# Build and publish
cd neural_memory
pip install build
python -m build
twine upload dist/*
```

### Option 4: Docker

Create a Dockerfile:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8501

CMD ["streamlit", "run", "dashboard.py", "--server.port", "8501", "--server.headless", "true"]
```

Build and publish:

```bash
docker build -t yourusername/neural-memory:latest .
docker push yourusername/neural-memory:latest
```

Users can then run:

```bash
docker run -p 8501:8501 \
  -v ~/.plur/neural_memory:/app/data \
  -v ~/.hermes/config.yaml:/app/config.yaml \
  yourusername/neural-memory:latest
```

## User Installation Guide

### Prerequisites

- Python 3.9+
- Hermes Agent installed
- (Optional) PLUR installed

### Step 1: Install NeuralMemory

```bash
# Clone the repository
git clone https://github.com/yourusername/neural-memory.git ~/.hermes/skills/neural-memory

# Or install via pip
pip install neural-memory

# Or install via Hermes skill tap
hermes skills tap add https://github.com/yourusername/neural-memory
```

### Step 2: Configure PostToolUse Hook

Add to `~/.hermes/config.yaml`:

```yaml
hooks:
  post_tool_call:
    - command: "python3 ~/.hermes/skills/neural-memory/hooks/capture.py"
      timeout: 5

capture:
  enabled: true
  max_events_per_session: 100
  filter_patterns:
    - user_correction
    - debug_breakthrough
    - tool_discovery
    - user_preference
    - budget_constraint
```

### Step 3: Install Dependencies

```bash
python setup.py --auto
```

### Step 4: Start the Dashboard

```bash
streamlit run dashboard.py
# Access at http://localhost:8501
```

### Step 5: Use as MCP Server

```bash
# Add to Hermes config
hermes mcp add neural-memory --command python3 mcp_server.py

# Or add to config.yaml manually
# mcp:
#   servers:
#     neural-memory:
#       command: python3
#       args: [~/.hermes/skills/neural-memory/mcp_server.py]
#       env:
#         NEURAL_MEMORY_DIR: ~/.plur/neural_memory
```

## Configuration Reference

### config.yaml

```yaml
# PostToolUse hook
hooks:
  post_tool_call:
    - command: "python3 ~/.hermes/skills/neural-memory/hooks/capture.py"
      timeout: 5

# Capture settings
capture:
  enabled: true                    # Enable/disable capture
  max_events_per_session: 100     # Max events per session
  filter_patterns:                # Which patterns to capture
    - user_correction
    - debug_breakthrough
    - tool_discovery
    - user_preference
    - budget_constraint

# Storage settings
storage:
  engrams_db: ~/.plur/neural_memory/engrams.db
  bm25_index: ~/.plur/neural_memory/bm25_index.json
  vector_store: ~/.plur/neural_memory/vector_store.db

# Search settings
search:
  bm25_k1: 1.5
  bm25_b: 0.75
  vector_model: all-MiniLM-L6-v2
  hybrid_rrf_k: 60
  hybrid_bm25_weight: 0.6
  hybrid_vector_weight: 0.4

# Decay settings
decay:
  enabled: true
  decay_rate: 0.95
  decay_interval_hours: 168       # Weekly
  tier_thresholds:
    procedural: 0.7
    semantic: 0.5
    episodic: 0.3
```

### Environment Variables

```bash
# Override default paths
export NEURAL_MEMORY_DIR=~/.plur/neural_memory
export NEURAL_MEMORY_CONFIG=~/.hermes/skills/neural-memory/config.yaml
```

## Troubleshooting

### Hook not firing

1. Check that `hooks.post_tool_call` is correctly configured in `~/.hermes/config.yaml`
2. Verify the hook script path is correct
3. Check Hermes logs for errors: `grep -i "post_tool_call" ~/.hermes/logs/agent.log`
4. Restart Hermes after making config changes

### Dashboard not starting

1. Check that Streamlit is installed: `pip install streamlit`
2. Check that all dependencies are installed: `python setup.py --auto`
3. Check port 8501 is not in use: `lsof -i :8501`

### MCP server not connecting

1. Check that the MCP server is running: `python mcp_server.py`
2. Check that the config.yaml has the correct MCP server configuration
3. Check Hermes logs for MCP errors: `grep -i "mcp" ~/.hermes/logs/agent.log`

### Database errors

1. Check that the database file exists: `ls -la ~/.plur/neural_memory/engrams.db`
2. Check that the database is not corrupted: `sqlite3 ~/.plur/neural_memory/engrams.db "SELECT COUNT(*) FROM engrams;"`
3. If corrupted, delete and recreate: `rm ~/.plur/neural_memory/engrams.db`

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

MIT License — see LICENSE file for details.
