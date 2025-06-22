#!/bin/bash

# DANDI SQL Database Deployment Script
# This script exports local database, compresses it, and uploads to Railway
# Usage: ./scripts/deploy_database.sh [--backup-first] [--help]

set -e  # Exit on any error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration from environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_DIR}/database_backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILENAME="dandi_db_backup_${TIMESTAMP}"
COMPRESSED_BACKUP="${BACKUP_FILENAME}.tar.gz"

# Load environment variables
if [ -f "${PROJECT_DIR}/.env" ]; then
    source "${PROJECT_DIR}/.env"
else
    echo -e "${RED}[ERROR]${NC} .env file not found in project directory"
    exit 1
fi

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
    echo "DANDI SQL Database Deployment Script"
    echo ""
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --backup-first   Create backup of Railway database before replacing"
    echo "  --help           Show this help message"
    echo ""
    echo "This script will:"
    echo "  1. Export local PostgreSQL database"
    echo "  2. Compress the database dump"
    echo "  3. Create backup of Railway database (if --backup-first specified)"
    echo "  4. Upload and restore data to Railway"
    echo "  5. Verify the data transfer"
    echo "  6. Clean up temporary files"
    echo ""
    echo "Prerequisites:"
    echo "  - Railway CLI installed (npm install -g @railway/cli)"
    echo "  - Railway project linked (railway link)"
    echo "  - PostgreSQL client tools (pg_dump, psql)"
    echo "  - .env file with local database credentials"
    echo ""
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if Railway CLI is installed
    if ! command -v railway &> /dev/null; then
        log_error "Railway CLI is not installed. Install with: npm install -g @railway/cli"
        exit 1
    fi
    
    # Check if pg_dump is available
    if ! command -v pg_dump &> /dev/null; then
        log_error "pg_dump is not available. Install PostgreSQL client tools."
        exit 1
    fi
    
    # Check if psql is available
    if ! command -v psql &> /dev/null; then
        log_error "psql is not available. Install PostgreSQL client tools."
        exit 1
    fi
    
    # Check if Railway project is linked
    if ! railway status &> /dev/null; then
        log_error "Railway project not linked. Run 'railway link' first."
        exit 1
    fi
    
    # Check environment variables
    if [ -z "$DB_NAME" ] || [ -z "$DB_USER" ] || [ -z "$DB_HOST" ] || [ -z "$DB_PORT" ]; then
        log_error "Required database environment variables not set in .env file"
        exit 1
    fi
    
    log_success "All prerequisites satisfied"
}

create_backup_directory() {
    log_info "Creating backup directory..."
    mkdir -p "$BACKUP_DIR"
    log_success "Backup directory ready: $BACKUP_DIR"
}

export_local_database() {
    log_info "Exporting local database..."
    
    local dump_file="${BACKUP_DIR}/${BACKUP_FILENAME}.sql"
    
    # Export database with proper options
    PGPASSWORD="$DB_PASSWORD" pg_dump \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        --verbose \
        --clean \
        --if-exists \
        --create \
        --encoding=UTF8 \
        --no-owner \
        --no-privileges \
        --file="$dump_file"
    
    if [ $? -eq 0 ]; then
        log_success "Database exported to: $dump_file"
        echo "File size: $(du -h "$dump_file" | cut -f1)"
    else
        log_error "Failed to export database"
        exit 1
    fi
}

create_django_fixture() {
    log_info "Creating Django fixture for additional safety..."
    
    cd "$PROJECT_DIR"
    
    # Create Django fixture as backup method
    local fixture_file="${BACKUP_DIR}/${BACKUP_FILENAME}_fixture.json"
    
    python manage.py dumpdata \
        --indent 2 \
        --exclude auth.permission \
        --exclude contenttypes \
        --exclude sessions \
        --exclude admin.logentry \
        --output "$fixture_file"
    
    if [ $? -eq 0 ]; then
        log_success "Django fixture created: $fixture_file"
    else
        log_warning "Failed to create Django fixture (SQL dump will be used)"
    fi
}

compress_backup() {
    log_info "Compressing backup files..."
    
    cd "$BACKUP_DIR"
    
    # Compress all backup files
    tar -czf "$COMPRESSED_BACKUP" "${BACKUP_FILENAME}"*
    
    if [ $? -eq 0 ]; then
        log_success "Backup compressed: ${BACKUP_DIR}/${COMPRESSED_BACKUP}"
        echo "Compressed size: $(du -h "${BACKUP_DIR}/${COMPRESSED_BACKUP}" | cut -f1)"
        
        # Remove uncompressed files to save space
        rm -f "${BACKUP_FILENAME}"*
    else
        log_error "Failed to compress backup"
        exit 1
    fi
}

backup_railway_database() {
    if [ "$BACKUP_RAILWAY" = "true" ]; then
        log_info "Creating backup of current Railway database..."
        
        local railway_backup="${BACKUP_DIR}/railway_backup_${TIMESTAMP}.json"
        
        # Create Django fixture backup from Railway
        railway run python manage.py dumpdata \
            --indent 2 \
            --exclude auth.permission \
            --exclude contenttypes \
            --exclude sessions \
            --exclude admin.logentry \
            --output "$railway_backup"
        
        if [ $? -eq 0 ]; then
            log_success "Railway database backed up to: $railway_backup"
        else
            log_warning "Failed to backup Railway database"
        fi
    fi
}

upload_to_railway() {
    log_info "Uploading database to Railway..."
    
    cd "$PROJECT_DIR"
    
    # Extract the compressed backup
    cd "$BACKUP_DIR"
    tar -xzf "$COMPRESSED_BACKUP"
    
    local sql_file="${BACKUP_DIR}/${BACKUP_FILENAME}.sql"
    
    if [ -f "$sql_file" ]; then
        log_info "Restoring database via Railway CLI..."
        
        # Copy SQL file to project directory temporarily for Railway access
        cp "$sql_file" "${PROJECT_DIR}/temp_restore.sql"
        
        cd "$PROJECT_DIR"
        
        # Add the file to git temporarily (Railway needs it in the repo)
        git add temp_restore.sql
        git commit -m "Temporary database restore file" || true
        git push origin main || log_warning "Could not push temp file to git"
        
        # Wait for deployment
        log_info "Waiting for Railway deployment..."
        sleep 30
        
        # Restore database using Railway CLI
        railway run bash -c "
            echo 'Connecting to PostgreSQL and restoring database...'
            cat temp_restore.sql | railway connect postgres
        "
        
        if [ $? -eq 0 ]; then
            log_success "Database restored successfully to Railway"
        else
            log_error "Failed to restore database to Railway"
            
            # Try alternative method using Django fixture if available
            local fixture_file="${BACKUP_DIR}/${BACKUP_FILENAME}_fixture.json"
            if [ -f "$fixture_file" ]; then
                log_info "Trying alternative restore using Django fixture..."
                
                cp "$fixture_file" "${PROJECT_DIR}/temp_fixture.json"
                git add temp_fixture.json
                git commit -m "Temporary fixture file" || true
                git push origin main || true
                
                sleep 20
                
                railway run python manage.py loaddata temp_fixture.json
                
                if [ $? -eq 0 ]; then
                    log_success "Database restored using Django fixture"
                else
                    log_error "Both restore methods failed"
                    exit 1
                fi
                
                # Clean up fixture file
                rm -f temp_fixture.json
                git rm temp_fixture.json || true
                git commit -m "Remove temporary fixture file" || true
                git push origin main || true
            else
                exit 1
            fi
        fi
        
        # Clean up SQL file
        rm -f temp_restore.sql
        git rm temp_restore.sql || true
        git commit -m "Remove temporary restore file" || true
        git push origin main || true
        
    else
        log_error "SQL dump file not found: $sql_file"
        exit 1
    fi
}

verify_data_transfer() {
    log_info "Verifying data transfer..."
    
    # Get counts from Railway database
    log_info "Checking data counts on Railway..."
    
    railway run python manage.py shell -c "
from dandisets.models import Dandiset, Asset, Contributor
print(f'Dandisets: {Dandiset.objects.count()}')
print(f'Assets: {Asset.objects.count()}')
print(f'Contributors: {Contributor.objects.count()}')
"
    
    if [ $? -eq 0 ]; then
        log_success "Data verification completed"
    else
        log_warning "Could not verify data counts"
    fi
}

cleanup_temporary_files() {
    log_info "Cleaning up temporary files..."
    
    cd "$BACKUP_DIR"
    
    # Remove extracted files but keep compressed backup
    rm -f "${BACKUP_FILENAME}"*.sql
    rm -f "${BACKUP_FILENAME}"*.json
    
    log_success "Temporary files cleaned up"
    log_info "Compressed backup preserved at: ${BACKUP_DIR}/${COMPRESSED_BACKUP}"
}

show_completion_message() {
    echo ""
    log_success "Database deployment completed successfully!"
    echo ""
    echo "Summary:"
    echo "  - Local database exported and compressed"
    echo "  - Data uploaded to Railway deployment"
    echo "  - Backup preserved at: ${BACKUP_DIR}/${COMPRESSED_BACKUP}"
    echo ""
    echo "Next steps:"
    echo "  1. Test your Railway application: railway open"
    echo "  2. Monitor logs for any issues: railway logs --tail"
    echo "  3. Run any additional migrations if needed"
    echo ""
    echo "Useful commands:"
    echo "  - Check app status: railway status"
    echo "  - View logs: railway logs"
    echo "  - Connect to database: railway connect postgres"
    echo "  - Run management commands: railway run python manage.py <command>"
    echo ""
}

# Parse command line arguments
BACKUP_RAILWAY="false"
while [[ $# -gt 0 ]]; do
    case $1 in
        --backup-first)
            BACKUP_RAILWAY="true"
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
    log_info "Starting database deployment to Railway..."
    echo "Timestamp: $TIMESTAMP"
    echo ""
    
    check_prerequisites
    create_backup_directory
    backup_railway_database
    export_local_database
    create_django_fixture
    compress_backup
    upload_to_railway
    verify_data_transfer
    cleanup_temporary_files
    show_completion_message
}

# Run main function
main "$@"
