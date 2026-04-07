#!/usr/bin/env bash
# =============================================================================
# A1SI-AITP — WSL Production Environment Setup
#
# Installs all system dependencies, configures Doppler secrets management,
# and brings up the production environment in Docker containers.
#
# Usage:
#   bash scripts/setup_wsl_prod.sh          # Full setup + deploy
#   bash scripts/setup_wsl_prod.sh --check  # Check prerequisites only
#   bash scripts/setup_wsl_prod.sh --deps   # Install dependencies only
#   bash scripts/setup_wsl_prod.sh --deploy # Build + deploy only (skip deps)
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="$ROOT_DIR/setup_wsl_prod.log"

# ── Colors & helpers ─────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${BLUE}→${NC} $*"; }
ok()    { echo -e "${GREEN}✓${NC} $*"; }
warn()  { echo -e "${YELLOW}⚠${NC} $*"; }
fail()  { echo -e "${RED}✗${NC} $*"; }
header(){ echo -e "\n${BOLD}═══ $* ═══${NC}"; }

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"; }

check_cmd() {
    if command -v "$1" &>/dev/null; then
        ok "$1 found: $($1 --version 2>/dev/null | head -1)"
        return 0
    else
        fail "$1 not found"
        return 1
    fi
}

need_sudo() {
    if [ "$(id -u)" -eq 0 ]; then
        return 0
    fi
    if sudo -n true 2>/dev/null; then
        return 0
    fi
    warn "Some steps require sudo. You may be prompted for your password."
    sudo true
}

# ── Prerequisite checks ─────────────────────────────────────────────────────

check_prerequisites() {
    header "Checking Prerequisites"
    local missing=0

    # WSL check
    if grep -qi microsoft /proc/version 2>/dev/null; then
        ok "Running in WSL"
    else
        warn "Not running in WSL — script designed for WSL but may work on native Linux"
    fi

    # Docker
    if check_cmd docker; then
        if docker info &>/dev/null; then
            ok "Docker daemon is running"
        else
            fail "Docker installed but daemon not running"
            warn "Start Docker Desktop or run: sudo service docker start"
            missing=1
        fi
    else
        missing=1
    fi

    # Docker Compose (v2 plugin)
    if docker compose version &>/dev/null; then
        ok "Docker Compose v2: $(docker compose version --short 2>/dev/null)"
    else
        fail "Docker Compose v2 not available"
        missing=1
    fi

    # Python
    check_cmd python3 || missing=1

    # Node.js
    check_cmd node || missing=1

    # npm
    check_cmd npm || missing=1

    # Doppler
    check_cmd doppler || missing=1

    # Make
    check_cmd make || missing=1

    # curl
    check_cmd curl || missing=1

    # git
    check_cmd git || missing=1

    echo ""
    if [ "$missing" -eq 0 ]; then
        ok "All prerequisites satisfied"
    else
        fail "Missing prerequisites detected"
    fi
    return $missing
}

# ── Install system packages ──────────────────────────────────────────────────

install_system_packages() {
    header "Installing System Packages"
    need_sudo

    info "Updating apt package index..."
    sudo apt-get update -qq 2>> "$LOG_FILE"

    local pkgs=(
        # Build essentials
        build-essential
        curl
        wget
        git
        make
        # Python build deps
        python3
        python3-pip
        python3-venv
        python3-dev
        libffi-dev
        # Docker deps (if installing from apt)
        ca-certificates
        gnupg
        lsb-release
        # Misc
        jq
        unzip
    )

    info "Installing base packages..."
    sudo apt-get install -y -qq "${pkgs[@]}" 2>> "$LOG_FILE"
    ok "System packages installed"
}

# ── Install Docker ───────────────────────────────────────────────────────────

install_docker() {
    header "Installing Docker"

    if command -v docker &>/dev/null && docker info &>/dev/null; then
        ok "Docker already installed and running"
        return 0
    fi

    # Check if Docker Desktop is handling Docker (common on WSL)
    if grep -qi microsoft /proc/version 2>/dev/null; then
        warn "WSL detected. Docker Desktop for Windows is recommended."
        warn "Install from: https://docs.docker.com/desktop/install/windows-install/"
        warn "Enable WSL 2 backend in Docker Desktop settings."
        echo ""
        read -rp "Is Docker Desktop installed and running? [y/N] " ans
        if [[ "$ans" =~ ^[Yy] ]]; then
            if docker info &>/dev/null; then
                ok "Docker Desktop connection verified"
                return 0
            else
                fail "Docker Desktop not reachable from WSL"
                warn "In Docker Desktop → Settings → Resources → WSL Integration"
                warn "Enable integration for your WSL distro"
                return 1
            fi
        fi
    fi

    # Fallback: install Docker Engine in WSL
    info "Installing Docker Engine via apt..."
    need_sudo

    # Add Docker's official GPG key
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    # Add the repository
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
        $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
        sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update -qq 2>> "$LOG_FILE"
    sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin 2>> "$LOG_FILE"

    # Add current user to docker group
    if ! groups "$USER" | grep -q docker; then
        sudo usermod -aG docker "$USER"
        warn "Added $USER to docker group. You may need to log out and back in."
    fi

    # Start Docker
    sudo service docker start 2>/dev/null || true

    ok "Docker Engine installed"
}

# ── Install Node.js ──────────────────────────────────────────────────────────

install_node() {
    header "Installing Node.js"

    if command -v node &>/dev/null; then
        local node_major
        node_major=$(node -v | sed 's/v//' | cut -d. -f1)
        if [ "$node_major" -ge 20 ]; then
            ok "Node.js $(node -v) already installed (>= 20 required)"
            return 0
        else
            warn "Node.js $(node -v) is too old, upgrading to 20.x..."
        fi
    fi

    need_sudo
    info "Installing Node.js 20.x via NodeSource..."

    # NodeSource setup
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - 2>> "$LOG_FILE"
    sudo apt-get install -y -qq nodejs 2>> "$LOG_FILE"

    ok "Node.js $(node -v) installed"
    ok "npm $(npm -v) installed"
}

# ── Install Doppler CLI ──────────────────────────────────────────────────────

install_doppler() {
    header "Installing Doppler CLI"

    if command -v doppler &>/dev/null; then
        ok "Doppler already installed: $(doppler --version 2>/dev/null)"
        return 0
    fi

    need_sudo
    info "Installing Doppler CLI..."

    # Official Doppler install script
    curl -sLf --retry 3 --tlsv1.2 --proto "=https" \
        "https://cli.doppler.com/install.sh" | sudo sh 2>> "$LOG_FILE"

    if command -v doppler &>/dev/null; then
        ok "Doppler installed: $(doppler --version 2>/dev/null)"
    else
        fail "Doppler installation failed"
        return 1
    fi
}

# ── Configure Doppler ────────────────────────────────────────────────────────

configure_doppler() {
    header "Configuring Doppler"

    # Check if already authenticated
    if doppler me &>/dev/null 2>&1; then
        ok "Doppler already authenticated"
        info "Logged in as: $(doppler me --json 2>/dev/null | jq -r '.workplace.name // "unknown"')"
    else
        info "Doppler requires authentication."
        info "A browser window will open for login."
        echo ""
        doppler login
        echo ""
        if doppler me &>/dev/null 2>&1; then
            ok "Doppler authentication successful"
        else
            fail "Doppler authentication failed"
            return 1
        fi
    fi

    # Link project
    info "Linking Doppler to project 'aitp'..."
    cd "$ROOT_DIR"

    # Check if project exists in Doppler
    if doppler projects get aitp &>/dev/null 2>&1; then
        ok "Doppler project 'aitp' found"
    else
        warn "Doppler project 'aitp' not found"
        info "Creating project 'aitp' in Doppler..."
        doppler projects create aitp --description "A1SI-AITP Trading Platform" 2>> "$LOG_FILE" || {
            fail "Could not create Doppler project. Create it manually at https://dashboard.doppler.com"
            return 1
        }
        ok "Project 'aitp' created"
    fi

    # Link to project aitp, dev config (single config used for all environments)
    doppler setup --project aitp --config dev --no-interactive 2>/dev/null || {
        warn "Auto-setup failed. Running interactive setup..."
        doppler setup --project aitp
    }
    ok "Doppler linked to project aitp (dev config)"

    # Verify required secrets exist
    echo ""
    info "Checking required production secrets in Doppler..."
    local required_secrets=(
        DJANGO_SECRET_KEY
        DJANGO_ENCRYPTION_KEY
        POSTGRES_PASSWORD
        FREQTRADE_USERNAME
        FREQTRADE_PASSWORD
        FREQTRADE__API_SERVER__JWT_SECRET_KEY
    )
    local missing_secrets=()

    for secret in "${required_secrets[@]}"; do
        if doppler secrets get "$secret" --plain 2>/dev/null | grep -q .; then
            ok "  $secret ✓"
        else
            fail "  $secret — not set"
            missing_secrets+=("$secret")
        fi
    done

    if [ ${#missing_secrets[@]} -gt 0 ]; then
        echo ""
        warn "Missing ${#missing_secrets[@]} required secret(s)."
        read -rp "Generate and upload missing secrets to Doppler now? [Y/n] " ans
        if [[ ! "$ans" =~ ^[Nn] ]]; then
            generate_and_upload_secrets "${missing_secrets[@]}"
        else
            warn "Skipped. Set them manually before deploying:"
            warn "  doppler secrets set SECRET_NAME=value"
        fi
    else
        ok "All required secrets present"
    fi
}

# ── Generate & upload missing secrets ────────────────────────────────────────

generate_and_upload_secrets() {
    local secrets=("$@")
    info "Generating missing secrets..."

    for secret in "${secrets[@]}"; do
        local value=""
        case "$secret" in
            DJANGO_SECRET_KEY)
                value=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
                ;;
            DJANGO_ENCRYPTION_KEY)
                # Fernet key = 32 random bytes, base64url-encoded with = padding
                value=$(python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
                ;;
            POSTGRES_PASSWORD)
                value=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
                ;;
            FREQTRADE_USERNAME)
                value="freqtrader"
                ;;
            FREQTRADE_PASSWORD)
                value=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
                ;;
            FREQTRADE__API_SERVER__JWT_SECRET_KEY)
                value=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
                ;;
            *)
                warn "  No generator for $secret — skipping"
                continue
                ;;
        esac

        if [ -n "$value" ]; then
            doppler secrets set "$secret=$value" --silent 2>> "$LOG_FILE"
            ok "  $secret generated and uploaded"
        fi
    done

    ok "Secrets configured in Doppler"
}

# ── Verify Docker resources ──────────────────────────────────────────────────

check_docker_resources() {
    header "Checking Docker Resources"

    # Check available memory
    local mem_gb
    mem_gb=$(free -g | awk '/^Mem:/{print $2}')
    if [ "$mem_gb" -ge 10 ]; then
        ok "System memory: ${mem_gb}GB (recommended: 10GB+)"
    elif [ "$mem_gb" -ge 6 ]; then
        warn "System memory: ${mem_gb}GB (recommended: 10GB+, minimum: 6GB)"
    else
        fail "System memory: ${mem_gb}GB — insufficient for production (minimum: 6GB)"
        warn "Increase WSL memory in %USERPROFILE%/.wslconfig:"
        warn "  [wsl2]"
        warn "  memory=12GB"
        return 1
    fi

    # Check available disk
    local disk_avail
    disk_avail=$(df -BG "$ROOT_DIR" | awk 'NR==2{print $4}' | sed 's/G//')
    if [ "$disk_avail" -ge 20 ]; then
        ok "Available disk: ${disk_avail}GB"
    else
        warn "Available disk: ${disk_avail}GB (recommend 20GB+ for Docker images)"
    fi

    # Check Docker disk usage
    info "Docker disk usage:"
    docker system df 2>/dev/null || warn "Could not check Docker disk usage"
}

# ── Build & deploy production ────────────────────────────────────────────────

deploy_production() {
    header "Building & Deploying Production Environment"
    cd "$ROOT_DIR"

    # Verify Doppler is configured
    if ! doppler secrets get DJANGO_SECRET_KEY --plain &>/dev/null; then
        fail "Doppler secrets not accessible. Run setup first."
        return 1
    fi

    # Create bind-mounted directories with correct permissions.
    # The backend container runs as non-root 'appuser' — bind mounts from the host
    # override directories created in the Dockerfile, so they must exist and be writable.
    # Previous Docker runs may have created root-owned dirs, so fix ownership first.
    info "Creating host directories for bind mounts..."
    local bind_dirs=(
        "$ROOT_DIR/backend/data/logs"
        "$ROOT_DIR/data/processed"
        "$ROOT_DIR/models"
        "$ROOT_DIR/freqtrade/user_data"
    )
    for d in "${bind_dirs[@]}"; do
        if [ -d "$d" ] && [ ! -w "$d" ]; then
            info "  Fixing ownership on $d (root-owned from previous Docker run)..."
            sudo chown -R "$(id -u):$(id -g)" "$(dirname "$d")"
        fi
        mkdir -p "$d"
    done
    chmod -R 777 "$ROOT_DIR/backend/data"
    ok "Host directories ready"

    # Build production images
    info "Building production Docker images (this may take several minutes)..."
    doppler run -- docker compose -f docker-compose.prod.yml --profile trading build 2>&1 | tee -a "$LOG_FILE"
    ok "Production images built"

    # Stop any existing prod containers
    info "Stopping existing production containers (if any)..."
    doppler run -- docker compose -f docker-compose.prod.yml --profile trading --profile postgres down 2>> "$LOG_FILE" || true

    # Start production
    info "Starting production containers..."
    doppler run -- docker compose -f docker-compose.prod.yml up -d 2>&1 | tee -a "$LOG_FILE"

    # Wait for backend health
    info "Waiting for backend to become healthy (up to 120s)..."
    local healthy=false
    for i in $(seq 1 40); do
        local status
        status=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{end}}' aitp-prod-backend 2>/dev/null || echo "unknown")
        if [ "$status" = "healthy" ]; then
            healthy=true
            break
        fi
        printf "  [%02d/40] Backend status: %s\r" "$i" "$status"
        sleep 3
    done
    echo ""

    if [ "$healthy" = true ]; then
        ok "Backend is healthy"
    else
        fail "Backend did not become healthy within 120s"
        warn "Check logs: doppler run -- docker compose -f docker-compose.prod.yml logs backend"
        return 1
    fi

    # Ensure frontend is started (depends on backend health)
    doppler run -- docker compose -f docker-compose.prod.yml start frontend 2>/dev/null || true

    # Smoke test
    echo ""
    info "Running smoke test..."
    sleep 2
    local health_response
    if health_response=$(curl -sf http://localhost:4100/api/health/ 2>/dev/null); then
        ok "Backend API healthy: $(echo "$health_response" | python3 -m json.tool 2>/dev/null | head -5)"
    else
        fail "Backend API not responding at http://localhost:4100/api/health/"
        warn "Check logs: make docker-prod-logs"
    fi

    if curl -sf http://localhost:4101/ &>/dev/null; then
        ok "Frontend serving at http://localhost:4101/"
    else
        fail "Frontend not responding at http://localhost:4101/"
    fi
}

# ── Print summary ────────────────────────────────────────────────────────────

print_summary() {
    header "Production Environment Summary"

    echo ""
    echo -e "${BOLD}Services:${NC}"
    docker ps --filter "name=aitp-prod-" --format "  {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "  No containers running"

    echo ""
    echo -e "${BOLD}Endpoints:${NC}"
    echo "  Backend API:  http://localhost:4100"
    echo "  Frontend UI:  http://localhost:4101"
    echo "  Health check: http://localhost:4100/api/health/"

    echo ""
    echo -e "${BOLD}Useful commands:${NC}"
    echo "  make docker-prod-up        # Start prod containers"
    echo "  make docker-prod-down      # Stop prod containers"
    echo "  make docker-prod-deploy    # Full rebuild + deploy"
    echo "  make docker-prod-logs      # Tail prod logs"
    echo "  make prod-trading-up       # Start trading bots"
    echo "  make docker-status         # Show all container status"
    echo "  doppler secrets             # List Doppler secrets"

    echo ""
    echo -e "${BOLD}Log file:${NC} $LOG_FILE"
    echo ""
}

# ── Main ─────────────────────────────────────────────────────────────────────

main() {
    echo ""
    echo -e "${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}║  A1SI-AITP — WSL Production Environment Setup      ║${NC}"
    echo -e "${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
    log "=== Setup started ==="

    local mode="${1:-full}"

    case "$mode" in
        --check)
            check_prerequisites
            exit $?
            ;;
        --deps)
            install_system_packages
            install_docker
            install_node
            install_doppler
            configure_doppler
            check_docker_resources
            ok "Dependencies installed. Run with --deploy to build and start containers."
            exit 0
            ;;
        --deploy)
            if ! check_prerequisites; then
                fail "Prerequisites not met. Run without flags for full setup."
                exit 1
            fi
            deploy_production
            print_summary
            exit 0
            ;;
        full|"")
            ;;
        *)
            echo "Usage: $0 [--check | --deps | --deploy]"
            echo ""
            echo "  (no flag)  Full setup: install deps + configure Doppler + deploy"
            echo "  --check    Check prerequisites only"
            echo "  --deps     Install dependencies only (no deploy)"
            echo "  --deploy   Build and deploy only (assumes deps installed)"
            exit 1
            ;;
    esac

    # Full setup
    install_system_packages
    install_docker
    install_node
    install_doppler
    configure_doppler
    check_docker_resources
    echo ""
    read -rp "All dependencies ready. Deploy production now? [Y/n] " ans
    if [[ "$ans" =~ ^[Nn] ]]; then
        ok "Setup complete. Run 'bash scripts/setup_wsl_prod.sh --deploy' when ready."
        exit 0
    fi
    deploy_production
    print_summary

    log "=== Setup completed ==="
    ok "Production environment is running."
}

main "$@"
