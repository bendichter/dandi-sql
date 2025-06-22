#!/bin/bash

# DANDI SQL Database Deployment Script (Django Method)
# This script uses Django fixtures to safely transfer data to Railway
# Usage: ./scripts/deploy_database_django.sh [--help]

set -e  # Exit on any error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_DIR}/database_backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
FIXTURE_FILE="dandi_data_${TIMESTAMP}.json"
COMPRESSED_FILE="dandi_data_${TIMESTAMP}.tar.gz"

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

print_help() {
    echo "DANDI SQL Database Deployment Script (Django Method)"
    echo ""
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --help           Show this help message"
    echo ""
    echo "This script will:"
    echo "  1. Export local database using Django fixtures"
    echo "  2. Compress the fixture file"
    echo "  3. Upload fixture to Railway via git"
    echo "  4. Load data into Railway database"
    echo "  5. Verify the data transfer"
    echo "  6. Clean up temporary files"
    echo ""
    echo "Prerequisites:"
    echo "  - Railway CLI installed (npm install -g @railway/cli)"
    echo "  - Railway project linked (railway link)"
    echo "  - Git repository properly configured"
    echo ""
    echo "Advantages of Django method:"
    echo "  - More reliable for Railway deployments"
    echo "  - Handles Django-specific data properly"
    echo "  - Smaller file sizes than SQL dumps"
    echo "  - Better error handling for foreign keys"
    echo ""
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if Railway CLI is installed
    if ! command -v railway &> /dev/null; then
        log_error "Railway CLI is not installed. Install with: npm install -g @railway/cli"
        exit 1
    fi
    
    # Check if git is available
    if ! command -v git &> /dev/null; then
        log_error "Git is not available. Please install git."
        exit 1
    fi
    
    # Check if Railway project is linked
    if ! railway status &> /dev/null; then
        log_error "Railway project not linked. Run 'railway link' first."
        exit 1
    fi
    
    # Check if we're in a git repository
    if ! git status &> /dev/null; then
        log_error "Not in a git repository. Please initialize git first."
        exit 1
    fi
    
    log_success "All prerequisites satisfied"
}

create_backup_directory() {
    log_info "Creating backup directory..."
    mkdir -p "$BACKUP_DIR"
    log_success "Backup directory ready: $BACKUP_DIR"
}

export_django_data() {
    log_info "Exporting data using Django fixtures..."
    
    cd "$PROJECT_DIR"
    
    local fixture_path="${BACKUP_DIR}/${FIXTURE_FILE}"
    
    # Export all relevant data excluding system tables
    python manage.py dumpdata \
        --indent 2 \
        --exclude auth.permission \
        --exclude contenttypes \
        --exclude sessions.session \
        --exclude admin.logentry \
        --exclude authtoken.token \
        --output "$fixture_path"
    
    if [ $? -eq 0 ]; then
        log_success "Data exported to: $fixture_path"
        echo "File size: $(du -h "$fixture_path" | cut -f1)"
        echo "Records: $(grep -c '"model":' "$fixture_path" || echo "Unknown")"
    else
        log_error "Failed to export Django data"
        exit 1
    fi
}

create_app_specific_fixtures() {
    log_info "Creating app-specific fixtures for better reliability..."
    
    cd "$PROJECT_DIR"
    
    # Export dandisets app separately for safety
    local dandisets_fixture="${BACKUP_DIR}/dandisets_${TIMESTAMP}.json"
    
    python manage.py dumpdata dandisets \
        --indent 2 \
        --output "$dandisets_fixture"
    
    if [ $? -eq 0 ]; then
        log_success "Dandisets data exported to: $dandisets_fixture"
    else
        log_warning "Failed to export dandisets-specific data"
    fi
    
    # Export auth data separately (users, groups)
    local auth_fixture="${BACKUP_DIR}/auth_${TIMESTAMP}.json"
    
    python manage.py dumpdata auth.user auth.group \
        --indent 2 \
        --output "$auth_fixture"
    
    if [ $? -eq 0 ]; then
        log_success "Auth data exported to: $auth_fixture"
    else
        log_warning "Failed to export auth data"
    fi
}

compress_fixtures() {
    log_info "Compressing fixture files..."
    
    cd "$BACKUP_DIR"
    
    # Compress all fixture files for this timestamp
    tar -czf "$COMPRESSED_FILE" *_${TIMESTAMP}.json
    
    if [ $? -eq 0 ]; then
        log_success "Fixtures compressed: ${BACKUP_DIR}/${COMPRESSED_FILE}"
        echo "Compressed size: $(du -h "${BACKUP_DIR}/${COMPRESSED_FILE}" | cut -f1)"
    else
        log_error "Failed to compress fixtures"
        exit 1
    fi
}

backup_railway_data() {
    log_info "Creating backup of current Railway data..."
    
    local railway_backup="${BACKUP_DIR}/railway_backup_${TIMESTAMP}.json"
    
    railway run python manage.py dumpdata \
        --indent 2 \
        --exclude auth.permission \
        --exclude contenttypes \
        --exclude sessions.session \
        --exclude admin.logentry \
        > "$railway_backup"
    
    if [ $? -eq 0 ] && [ -s "$railway_backup" ]; then
        log_success "Railway data backed up to: $railway_backup"
    else
        log_warning "Could not backup Railway data (might be empty database)"
        rm -f "$railway_backup"
    fi
}

upload_and_load_data() {
    log_info "Uploading and loading data to Railway..."
    
    cd "$PROJECT_DIR"
    
    # Copy the main fixture file to project directory
    cp "${BACKUP_DIR}/${FIXTURE_FILE}" "./temp_fixture.json"
    
    # Add to git and push
    git add temp_fixture.json
    git commit -m "Add database fixture for Railway deployment - ${TIMESTAMP}"
    
    log_info "Pushing fixture to git repository..."
    git push origin main
    
    if [ $? -ne 0 ]; then
        log_error "Failed to push fixture to git"
        exit 1
    fi
    
    # Wait for Railway deployment
    log_info "Waiting for Railway deployment to complete..."
    sleep 30
    
    # Clear existing data (if any) and load new data
    log_info "Loading fixture data into Railway database..."
    
    railway run python manage.py flush --noinput || log_warning "Flush command failed (database might be empty)"
    
    # Load the fixture
    railway run python manage.py loaddata temp_fixture.json
    
    if [ $? -eq 0 ]; then
        log_success "Data loaded successfully into Railway database"
    else
        log_error "Failed to load data into Railway database"
        
        # Try loading app-specific fixtures separately
        log_info "Trying to load app-specific fixtures..."
        
        # Copy and load dandisets fixture
        if [ -f "${BACKUP_DIR}/dandisets_${TIMESTAMP}.json" ]; then
            cp "${BACKUP_DIR}/dandisets_${TIMESTAMP}.json" "./temp_dandisets.json"
            git add temp_dandisets.json
            git commit -m "Add dandisets fixture"
            git push origin main
            sleep 15
            
            railway run python manage.py loaddata temp_dandisets.json
            
            if [ $? -eq 0 ]; then
                log_success "Dandisets data loaded successfully"
            else
                log_error "Failed to load dandisets data"
            fi
            
            # Clean up
            rm -f temp_dandisets.json
            git rm temp_dandisets.json
            git commit -m "Remove temporary dandisets fixture"
        fi
        
        # Copy and load auth fixture
        if [ -f "${BACKUP_DIR}/auth_${TIMESTAMP}.json" ]; then
            cp "${BACKUP_DIR}/auth_${TIMESTAMP}.json" "./temp_auth.json"
            git add temp_auth.json
            git commit -m "Add auth fixture"
            git push origin main
            sleep 15
            
            railway run python manage.py loaddata temp_auth.json
            
            if [ $? -eq 0 ]; then
                log_success "Auth data loaded successfully"
            else
                log_warning "Failed to load auth data"
            fi
            
            # Clean up
            rm -f temp_auth.json
            git rm temp_auth.json
            git commit -m "Remove temporary auth fixture"
        fi
    fi
    
    # Clean up main fixture file
    rm -f temp_fixture.json
    git rm temp_fixture.json
    git commit -m "Remove temporary fixture file"
    git push origin main
}

verify_data_transfer() {
    log_info "Verifying data transfer..."
    
    # Check data counts
    railway run python manage.py shell -c "
from dandisets.models import Dandiset, Asset, Contributor
from django.contrib.auth.models import User

print('=== Data Verification ===')
print(f'Dandisets: {Dandiset.objects.count()}')
print(f'Assets: {Asset.objects.count()}')
print(f'Contributors: {Contributor.objects.count()}')
print(f'Users: {User.objects.count()}')
print('========================')

# Check for any recent dandisets
recent = Dandiset.objects.order_by('-created')[:3]
print('Recent Dandisets:')
for d in recent:
    print(f'  - {d.identifier}: {d.name[:50]}...')
"
    
    if [ $? -eq 0 ]; then
        log_success "Data verification completed"
    else
        log_warning "Could not verify data"
    fi
}

run_migrations() {
    log_info "Running any pending migrations on Railway..."
    
    railway run python manage.py migrate
    
    if [ $? -eq 0 ]; then
        log_success "Migrations completed"
    else
        log_warning "Migration issues detected"
    fi
}

cleanup_files() {
    log_info "Cleaning up temporary files..."
    
    # Remove individual fixture files but keep compressed backup
    rm -f "${BACKUP_DIR}"/*_${TIMESTAMP}.json
    
    log_success "Temporary files cleaned up"
    log_info "Compressed backup preserved: ${BACKUP_DIR}/${COMPRESSED_FILE}"
}

show_completion_message() {
    echo ""
    log_success "Django-based database deployment completed!"
    echo ""
    echo "Summary:"
    echo "  - Local data exported using Django fixtures"
    echo "  - Data uploaded and loaded into Railway"
    echo "  - Compressed backup: ${BACKUP_DIR}/${COMPRESSED_FILE}"
    echo ""
    echo "Next steps:"
    echo "  1. Test your Railway application: railway open"
    echo "  2. Create a superuser if needed: railway run python manage.py createsuperuser"
    echo "  3. Monitor application logs: railway logs --tail"
    echo ""
    echo "Useful commands:"
    echo "  - Django shell: railway run python manage.py shell"
    echo "  - Run management commands: railway run python manage.py <command>"
    echo "  - Check database: railway connect postgres"
    echo ""
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
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
    log_info "Starting Django-based database deployment to Railway..."
    echo "Timestamp: $TIMESTAMP"
    echo ""
    
    check_prerequisites
    create_backup_directory
    backup_railway_data
    export_django_data
    create_app_specific_fixtures
    compress_fixtures
    upload_and_load_data
    verify_data_transfer
    run_migrations
    cleanup_files
    show_completion_message
}

# Run main function
main "$@"
