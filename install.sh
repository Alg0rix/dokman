#!/usr/bin/env bash
# Dokman Installer & Upgrader
# Usage: curl -fsSL https://raw.githubusercontent.com/Alg0rix/dokman/main/install.sh | bash

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Print with color
info() {
    echo -e "${BLUE}${BOLD}info${NC}: $1"
}

success() {
    echo -e "${GREEN}${BOLD}success${NC}: $1"
}

warn() {
    echo -e "${YELLOW}${BOLD}warning${NC}: $1"
}

error() {
    echo -e "${RED}${BOLD}error${NC}: $1"
    exit 1
}

# Check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Detect OS
detect_os() {
    case "$(uname -s)" in
        Linux*)     OS="linux" ;;
        Darwin*)    OS="macos" ;;
        CYGWIN*|MINGW*|MSYS*) OS="windows" ;;
        *)          OS="unknown" ;;
    esac
    echo "$OS"
}

# Check Python version
check_python() {
    if command_exists python3; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
        PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
        
        if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 13 ]; }; then
            warn "Python $PYTHON_VERSION detected, but dokman requires Python 3.13+"
            return 1
        fi
        return 0
    fi
    return 1
}

# Install uv
install_uv() {
    info "Installing uv..."
    
    if command_exists curl; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command_exists wget; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        error "curl or wget is required to install uv"
    fi
    
    # Source the uv environment
    if [ -f "$HOME/.local/bin/env" ]; then
        source "$HOME/.local/bin/env"
    elif [ -f "$HOME/.cargo/env" ]; then
        source "$HOME/.cargo/env"
    fi
    
    # Add to PATH if not already there
    export PATH="$HOME/.local/bin:$PATH"
    
    if command_exists uv; then
        success "uv installed successfully"
    else
        error "Failed to install uv. Please install it manually: https://docs.astral.sh/uv/getting-started/installation/"
    fi
}

# Check if dokman is already installed
is_dokman_installed() {
    command_exists dokman || uv tool list 2>/dev/null | grep -q "^dokman"
}

# Main installation
main() {
    echo ""
    echo -e "${BOLD}╔════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}║         ${BLUE}Dokman Installer${NC}${BOLD}               ║${NC}"
    echo -e "${BOLD}║   Docker Compose Deployment Manager    ║${NC}"
    echo -e "${BOLD}╚════════════════════════════════════════╝${NC}"
    echo ""
    
    OS=$(detect_os)
    info "Detected OS: $OS"
    
    # Check for Docker
    if ! command_exists docker; then
        warn "Docker not found. Dokman requires Docker to function."
        warn "Please install Docker: https://docs.docker.com/get-docker/"
    fi
    
    # Check for uv and install if missing
    if ! command_exists uv; then
        warn "uv not found"
        install_uv
    else
        info "uv is already installed"
    fi
    
    # Check Python version
    if ! check_python; then
        warn "Python 3.13+ not found. uv will attempt to download it automatically."
    fi
    
    # Check if dokman is already installed - upgrade if so
    if is_dokman_installed; then
        info "dokman is already installed, upgrading..."
        if uv tool upgrade dokman; then
            success "dokman upgraded successfully!"
        else
            warn "Upgrade failed, attempting reinstall..."
            uv tool install --force --python 3.13 dokman || uv tool install --force dokman
            success "dokman reinstalled successfully!"
        fi
    else
        # Fresh install
        info "Installing dokman..."
        if uv tool install --python 3.13 dokman; then
            success "dokman installed successfully!"
        else
            # Try without specifying Python version (uv will find a compatible one)
            warn "Failed with Python 3.13, trying to auto-detect Python version..."
            if uv tool install dokman; then
                success "dokman installed successfully!"
            else
                error "Failed to install dokman. Please check your Python installation."
            fi
        fi
    fi
    
    # Verify installation
    echo ""
    if command_exists dokman; then
        INSTALLED_VERSION=$(dokman --version 2>/dev/null || echo "unknown")
        success "Installation complete! (${INSTALLED_VERSION})"
        echo ""
        echo -e "${BOLD}Getting started:${NC}"
        echo "  dokman --help              Show all available commands"
        echo "  dokman list                List registered projects"
        echo "  dokman register <path>     Register a Docker Compose project"
        echo "  dokman up                  Start a project"
        echo ""
        echo -e "${BOLD}To upgrade later:${NC}"
        echo "  uv tool upgrade dokman"
        echo ""
        echo -e "${BOLD}Documentation:${NC} https://github.com/Alg0rix/dokman"
        echo ""
    else
        warn "dokman installed but not found in PATH"
        echo ""
        echo "You may need to add the following to your shell profile:"
        echo ""
        echo "  For bash (~/.bashrc):"
        echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
        echo ""
        echo "  For zsh (~/.zshrc):"
        echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
        echo ""
        echo "  For fish (~/.config/fish/config.fish):"
        echo "    fish_add_path \$HOME/.local/bin"
        echo ""
        echo "Then restart your terminal or run: source ~/.bashrc (or equivalent)"
        echo ""
    fi
}

main "$@"
