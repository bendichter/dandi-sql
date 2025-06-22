#!/bin/bash

# Simple Database Export and Railway Deployment Script
# Usage: ./scripts/simple_deploy_db.sh

set -e  # Exit on any error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
EXPORT_FILE="dandi_db_export_${TIMESTAMP}.sql"
COMPRESSED_FILE="dandi_db_export_${TIMESTAMP}.tar.gz"

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

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if pg_dump is available
    if ! command -v pg_dump &> /dev/null; then
        log_error "pg_dump is not available. Install PostgreSQL client tools."
        exit 1
    fi
    
    # Check if Railway CLI is installed
    if ! command -v railway &> /dev/null; then
        log_error "Railway CLI is not installed. Install with: npm install -g @railway/cli"
        exit 1
    fi
    
    # Check if Railway project is linked
    if ! railway status &> /dev/null; then
        log_error "Railway project not linked. Run 'railway link' first."
        exit 1
    fi
    
    log_success "All prerequisites satisfied"
}

export_database() {
    log_info "Exporting local database..."
    
    # Use the exact command specified by user
    PGPASSWORD="mypass123!" pg_dump -h localhost -p 5432 -U bdichter -d dandi_db --verbose --no-owner --no-privileges -f "$EXPORT_FILE"
    
    if [ $? -eq 0 ] && [ -f "$EXPORT_FILE" ]; then
        log_success "Database exported to: $EXPORT_FILE"
        echo "File size: $(du -h "$EXPORT_FILE" | cut -f1)"
    else
        log_error "Failed to export database"
        exit 1
    fi
}

compress_export() {
    log_info "Compressing database export..."
    
    tar -czf "$COMPRESSED_FILE" "$EXPORT_FILE"
    
    if [ $? -eq 0 ]; then
        log_success "Export compressed to: $COMPRESSED_FILE"
        echo "Compressed size: $(du -h "$COMPRESSED_FILE" | cut -f1)"
        
        # Remove uncompressed file to save space
        rm -f "$EXPORT_FILE"
    else
        log_error "Failed to compress export"
        exit 1
    fi
}

backup_railway_database() {
    log_info "Creating backup of current Railway database..."
    
    local railway_backup="railway_backup_${TIMESTAMP}.json"
    
    railway run python manage.py dumpdata \
        --indent 2 \
        --exclude auth.permission \
        --exclude contenttypes \
        --exclude sessions.session \
        --exclude admin.logentry \
        > "$railway_backup" 2>/dev/null
    
    if [ $? -eq 0 ] && [ -s "$railway_backup" ]; then
        log_success "Railway database backed up to: $railway_backup"
    else
        log_warning "Could not backup Railway database (might be empty)"
        rm -f "$railway_backup"
    fi
}

upload_to_railway() {
    log_info "Uploading database to Railway..."
    
    # Extract the compressed file
    tar -xzf "$COMPRESSED_FILE"
    
    if [ ! -f "$EXPORT_FILE" ]; then
        log_error "Could not extract SQL file"
        exit 1
    fi
    
    # Add to git temporarily
    git add "$EXPORT_FILE"
    git commit -m "Temporary database export for Railway deployment - $TIMESTAMP"
    git push origin main
    
    if [ $? -ne 0 ]; then
        log_error "Failed to push export to git"
        exit 1
    fi
    
    # Wait for deployment
    log_info "Waiting for Railway deployment..."
    sleep 30
    
    # Upload to Railway PostgreSQL
    log_info "Restoring database on Railway..."
    
    railway run bash -c "
        echo 'Connecting to PostgreSQL and restoring database...'
        psql \$DATABASE_URL < $EXPORT_FILE
    "
    
    if [ $? -eq 0 ]; then
        log_success "Database restored successfully to Railway"
    else
        log_error "Failed to restore database to Railway"
        exit 1
    fi
    
    # Clean up git
    rm -f "$EXPORT_FILE"
    git rm "$EXPORT_FILE"
    git commit -m "Remove temporary database export file"
    git push origin main
}

verify_deployment() {
    log_info "Verifying deployment..."
    
    railway run python manage.py shell -c "
from dandisets.models import Dandiset, Asset, Contributor
from django.contrib.auth.models import User

print('=== Railway Database Status ===')
print(f'Dandisets: {Dandiset.objects.count()}')
print(f'Assets: {Asset.objects.count()}')
print(f'Contributors: {Contributor.objects.count()}')
print(f'Users: {User.objects.count()}')
print('==============================')
"
    
    if [ $? -eq 0 ]; then
        log_success "Deployment verification completed"
    else
        log_warning "Could not verify deployment"
    fi
}

cleanup() {
    log_info "Cleaning up temporary files..."
    
    # Keep compressed backup, remove extracted files
    rm -f "$EXPORT_FILE"
    
    log_success "Cleanup completed"
    log_info "Compressed backup preserved: $COMPRESSED_FILE"
}

show_completion() {
    echo ""
    log_success "Database deployment completed successfully!"
    echo ""
    echo "Summary:"
    echo "  - Local database exported using pg_dump"
    echo "  - Data compressed and uploaded to Railway"
    echo "  - Railway database replaced with local data"
    echo "  - Backup preserved: $COMPRESSED_FILE"
    echo ""
    echo "Next steps:"
    echo "  1. Test your Railway application: railway open"
    echo "  2. Monitor logs: railway logs --tail"
    echo "  3. Run migrations if needed: railway run python manage.py migrate"
    echo ""
}

# Main execution
main() {
    log_info "Starting simple database deployment to Railway..."
    echo "Timestamp: $TIMESTAMP"
    echo ""
    
    check_prerequisites
    backup_railway_database
    export_database
    compress_export
    upload_to_railway
    verify_deployment
    cleanup
    show_completion
}

# Run main function
main "$@"
