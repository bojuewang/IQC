#!/usr/bin/env bash
set -euo pipefail

# Run this script from the repo root: C:/Users/Wangb/IQC or /mnt/c/Users/Wangb/IQC
# Purpose: reorganize IQC into a cleaner quant-research repo structure.

mkdir -p \
  data/fields \
  data/operators \
  scraper/wqbrain \
  scraper/web_table \
  alpha/dsl \
  alpha/generator \
  alpha/examples \
  notebooks \
  pipeline

# Move field/operator data into stable locations.
if [ -d "ALPHA pipeline/Field" ]; then
  mv "ALPHA pipeline/Field"/*.csv data/fields/ 2>/dev/null || true
fi

if [ -d "ALPHA pipeline/Operator" ]; then
  mv "ALPHA pipeline/Operator"/* data/operators/ 2>/dev/null || true
fi

# Move scraper projects into stable English paths.
if [ -d "说明书制作爬虫脚本/wqbrain_full_scraper" ]; then
  mv "说明书制作爬虫脚本/wqbrain_full_scraper"/* scraper/wqbrain/ 2>/dev/null || true
fi

if [ -d "说明书制作爬虫脚本/web_table_llm_pipeline" ]; then
  mv "说明书制作爬虫脚本/web_table_llm_pipeline"/* scraper/web_table/ 2>/dev/null || true
fi

# Move alpha DSL scripts if they exist inside the old Chinese path.
OLD_ALPHA_DIR="scraper/web_table/爬虫脚本文件"
if [ -d "$OLD_ALPHA_DIR" ]; then
  mv "$OLD_ALPHA_DIR"/operator_dsl_layer.py alpha/dsl/ 2>/dev/null || true
  mv "$OLD_ALPHA_DIR"/alpha_pipeline.py alpha/generator/ 2>/dev/null || true
  mv "$OLD_ALPHA_DIR"/generated_alphas.txt alpha/examples/ 2>/dev/null || true
  mv "$OLD_ALPHA_DIR"/parse_operators.py alpha/dsl/ 2>/dev/null || true
fi

# Remove empty old directories if possible.
rmdir "ALPHA pipeline/Field" 2>/dev/null || true
rmdir "ALPHA pipeline/Operator" 2>/dev/null || true
rmdir "ALPHA pipeline" 2>/dev/null || true
rmdir "说明书制作爬虫脚本/wqbrain_full_scraper" 2>/dev/null || true
rmdir "说明书制作爬虫脚本/web_table_llm_pipeline" 2>/dev/null || true
rmdir "说明书制作爬虫脚本" 2>/dev/null || true

# Create a standard .gitignore.
cat > .gitignore <<'EOF'
# Python virtual environments
.venv/
**/.venv/

# Environment variables / secrets
.env
**/.env

# Python cache
__pycache__/
**/__pycache__/
*.pyc

# Jupyter
.ipynb_checkpoints/
**/.ipynb_checkpoints/

# Logs and local artifacts
logs/
**/logs/
anaconda_projects/
**/anaconda_projects/
*.db

# OS files
.DS_Store
Thumbs.db
EOF

# Create requirements.txt if missing.
if [ ! -f requirements.txt ]; then
  cat > requirements.txt <<'EOF'
pandas
numpy
requests
beautifulsoup4
lxml
python-dotenv
openai
EOF
fi

# Create README skeleton if missing.
if [ ! -f README.md ]; then
  cat > README.md <<'EOF'
# IQC Alpha Research Infrastructure

This repository contains a local research pipeline for IQC / WorldQuant-style alpha construction.

## Structure

```text
IQC/
├── data/
│   ├── fields/
│   └── operators/
├── scraper/
│   ├── wqbrain/
│   └── web_table/
├── alpha/
│   ├── dsl/
│   ├── generator/
│   └── examples/
├── notebooks/
├── pipeline/
├── requirements.txt
└── .gitignore
```

## Goal

Natural-language intuition → valid operator DSL → alpha expression → platform-ready submission.
EOF
fi

echo "Repo restructuring complete."
echo "Next commands:"
echo "  git status"
echo "  git add -A"
echo "  git commit -m 'refactor: reorganize IQC repo structure'"
echo "  git push"
