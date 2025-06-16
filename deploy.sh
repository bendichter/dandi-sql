#!/bin/bash

# DANDI SQL Deployment Script
# This script deploys the DANDI SQL Django application to a production server
# Usage: ./deploy.sh [--dev] [--help]

set -e  # Exit on any error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="dandi-sql"
APP_DIR="/opt/${APP_NAME}"
VENV_DIR="${APP_DIR}/venv"
LOG_DIR="/var/log/${APP_NAME}"
RUN_DIR="/var/run/${APP_NAME}"
SERVICE_USER="www-data"
SERVICE_GROUP="www-data"
DB_NAME="dandi_db"
DB_USER="dandi_user"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

print_help() {
    echo "DANDI SQL Deployment Script"
    echo ""
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --dev        Deploy in development mode (uses SQLite)"
    echo "  --help       Show this help message"
    echo ""
    echo "This script will:"
    echo "  1. Install system dependencies"
    echo "  2. Set up PostgreSQL database"
    echo "  3. Create application directory structure"
    echo "  4. Set up Python virtual environment"
    echo "  5. Install Python dependencies"
    echo "  6. Configure Django settings"
    echo "  7. Run database migrations"
    echo "  8. Collect static files"
    echo "  9. Set up systemd service"
    echo "  10. Configure Nginx"
    echo "  11. Set up cron job for DANDI sync"
    echo ""
}

install_system_dependencies() {
    log_info "Installing system dependencies..."
    
    # Update package list
    apt-get update
    
    # Install required packages
    apt-get install -y \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        postgresql \
        postgresql-contrib \
        postgresql-client \
        nginx \
        git \
        curl \
        build-essential \
        libpq-dev \
        supervisor \
        cron \
        logrotate
    
    log_success "System dependencies installed"
}

setup_database() {
    if [[ "$DEV_MODE" == "true" ]]; then
        log_info "Development mode: skipping PostgreSQL setup"
        return
    fi
    
    log_info "Setting up PostgreSQL database..."
    
    # Start PostgreSQL service
    systemctl start postgresql
    systemctl enable postgresql
    
    # Create database and user
    sudo -u postgres psql <<EOF
CREATE DATABASE ${DB_NAME};
CREATE USER ${DB_USER} WITH PASSWORD 'secure_password_change_me';
ALTER ROLE ${DB_USER} SET client_encoding TO 'utf8';
ALTER ROLE ${DB_USER} SET default_transaction_isolation TO 'read committed';
ALTER ROLE ${DB_USER} SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
\q
EOF
    
    log_success "Database setup completed"
    log_warning "Please change the database password in production!"
}

create_directories() {
    log_info "Creating application directories..."
    
    # Create main application directory
    mkdir -p ${APP_DIR}
    mkdir -p ${LOG_DIR}
    mkdir -p ${RUN_DIR}
    mkdir -p ${APP_DIR}/staticfiles
    mkdir -p ${APP_DIR}/media
    mkdir -p ${APP_DIR}/logs
    
    # Set ownership
    chown -R ${SERVICE_USER}:${SERVICE_GROUP} ${APP_DIR}
    chown -R ${SERVICE_USER}:${SERVICE_GROUP} ${LOG_DIR}
    chown -R ${SERVICE_USER}:${SERVICE_GROUP} ${RUN_DIR}
    
    log_success "Directories created"
}

copy_application() {
    log_info "Copying application files..."
    
    # Copy application files (assuming script is run from project directory)
    rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' --exclude='.env' ./ ${APP_DIR}/
    
    # Set ownership
    chown -R ${SERVICE_USER}:${SERVICE_GROUP} ${APP_DIR}
    
    log_success "Application files copied"
}

setup_python_environment() {
    log_info "Setting up Python virtual environment..."
    
    # Create virtual environment
    sudo -u ${SERVICE_USER} python3 -m venv ${VENV_DIR}
    
    # Install Python dependencies
    sudo -u ${SERVICE_USER} ${VENV_DIR}/bin/pip install --upgrade pip
    sudo -u ${SERVICE_USER} ${VENV_DIR}/bin/pip install -r ${APP_DIR}/requirements_production.txt
    
    log_success "Python environment setup completed"
}

configure_django() {
    log_info "Configuring Django..."
    
    # Create production environment file
    if [[ "$DEV_MODE" == "true" ]]; then
        cat > ${APP_DIR}/.env <<EOF
# Development environment
DEBUG=True
SECRET_KEY=$(python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
ALLOWED_HOSTS=localhost,127.0.0.1

# Database (SQLite for development)
DB_ENGINE=django.db.backends.sqlite3
DB_NAME=${APP_DIR}/db.sqlite3
EOF
    else
        cat > ${APP_DIR}/.env <<EOF
# Production environment
DEBUG=False
SECRET_KEY=$(python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
ALLOWED_HOSTS=localhost,127.0.0.1,your-domain.com

# Database
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_PASSWORD=secure_password_change_me
DB_HOST=localhost
DB_PORT=5432

# Email configuration (optional)
# EMAIL_HOST=smtp.your-provider.com
# EMAIL_PORT=587
# EMAIL_HOST_USER=your-email@domain.com
# EMAIL_HOST_PASSWORD=your-email-password
# EMAIL_USE_TLS=True
# ADMIN_EMAIL=admin@your-domain.com
EOF
    fi
    
    chown ${SERVICE_USER}:${SERVICE_GROUP} ${APP_DIR}/.env
    chmod 600 ${APP_DIR}/.env
    
    # Run Django setup commands
    cd ${APP_DIR}
    sudo -u ${SERVICE_USER} ${VENV_DIR}/bin/python manage.py migrate --settings=dandi_sql.settings_production
    sudo -u ${SERVICE_USER} ${VENV_DIR}/bin/python manage.py collectstatic --noinput --settings=dandi_sql.settings_production
    sudo -u ${SERVICE_USER} ${VENV_DIR}/bin/python manage.py createsuperuser --noinput --username admin --email admin@localhost --settings=dandi_sql.settings_production || true
    
    log_success "Django configuration completed"
}

setup_systemd_service() {
    log_info "Setting up systemd service..."
    
    # Copy service file
    cp ${APP_DIR}/deploy/dandi-sql.service /etc/systemd/system/
    
    # Reload systemd and enable service
    systemctl daemon-reload
    systemctl enable dandi-sql
    
    log_success "Systemd service configured"
}

setup_nginx() {
    log_info "Setting up Nginx..."
    
    # Copy Nginx configuration
    cp ${APP_DIR}/deploy/nginx-dandi-sql.conf /etc/nginx/sites-available/dandi-sql
    
    # Enable site
    ln -sf /etc/nginx/sites-available/dandi-sql /etc/nginx/sites-enabled/
    
    # Remove default site if it exists
    rm -f /etc/nginx/sites-enabled/default
    
    # Test Nginx configuration
    nginx -t
    
    # Enable and start Nginx
    systemctl enable nginx
    systemctl restart nginx
    
    log_success "Nginx configured"
}

setup_cron_job() {
    log_info "Setting up cron job for DANDI sync..."
    
    # Copy cron configuration
    cp ${APP_DIR}/deploy/dandi-sync-cron /etc/cron.d/dandi-sync
    chmod 644 /etc/cron.d/dandi-sync
    
    # Restart cron service
    systemctl restart cron
    
    log_success "Cron job configured"
}

start_services() {
    log_info "Starting services..."
    
    # Start the application
    systemctl start dandi-sql
    
    # Check service status
    if systemctl is-active --quiet dandi-sql; then
        log_success "DANDI SQL service started successfully"
    else
        log_error "Failed to start DANDI SQL service"
        systemctl status dandi-sql
        exit 1
    fi
}

show_completion_message() {
    echo ""
    log_success "Deployment completed successfully!"
    echo ""
    echo "Next steps:"
    echo "1. Update the domain name in /etc/nginx/sites-available/dandi-sql"
    echo "2. Update the database password in ${APP_DIR}/.env"
    echo "3. Configure SSL certificates for HTTPS (recommended)"
    echo "4. Test the application at http://localhost or your domain"
    echo "5. Monitor logs in ${LOG_DIR}/"
    echo ""
    echo "Useful commands:"
    echo "  - Check service status: systemctl status dandi-sql"
    echo "  - View logs: journalctl -u dandi-sql -f"
    echo "  - Restart service: systemctl restart dandi-sql"
    echo "  - Manual sync: cd ${APP_DIR} && sudo -u ${SERVICE_USER} ${VENV_DIR}/bin/python manage.py sync_dandi_incremental"
    echo ""
}

# Parse command line arguments
DEV_MODE="false"
while [[ $# -gt 0 ]]; do
    case $1 in
        --dev)
            DEV_MODE="true"
            shift
            ;;
        --help)
            print_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            print_help
            exit 1
            ;;
    esac
done

# Main deployment process
main() {
    log_info "Starting DANDI SQL deployment..."
    
    if [[ "$DEV_MODE" == "true" ]]; then
        log_info "Running in development mode"
    fi
    
    check_root
    install_system_dependencies
    setup_database
    create_directories
    copy_application
    setup_python_environment
    configure_django
    setup_systemd_service
    setup_nginx
    setup_cron_job
    start_services
    show_completion_message
}

# Run main function
main "$@"
