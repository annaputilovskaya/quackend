#!/usr/bin/env bash

set -e

CYAN='\033[0;36m'
BLUE='\033[0;34m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${CYAN}=== Running Definition of Done (Quackend) ===${NC}"

echo -e "${BLUE}[1/5] Checking Layer Contracts (import-linter)...${NC}"
lint-imports

echo -e "${BLUE}[2/5] Linting Code (ruff)...${NC}"
ruff check .

echo -e "${BLUE}[3/5] Checking Code Format (ruff format)...${NC}"
ruff format --check .

echo -e "${BLUE}[4/5] Verifying Static Types (mypy)...${NC}"
mypy src

echo -e "${BLUE}[5/5] Running Tests & Coverage (pytest)...${NC}"
python -m coverage run -m pytest
python -m coverage report --fail-under=80

echo -e "${GREEN}SUCCESS: All DoD checks passed! Ready to commit.${NC}"
exit 0