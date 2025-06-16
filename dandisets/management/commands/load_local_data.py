"""
Management command to load data from fixtures uploaded to Railway
"""

import os
import json
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.conf import settings


class Command(BaseCommand):
    help = 'Load data from uploaded fixtures'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fixture-file',
            type=str,
            help='Path to fixture file to load',
            default='data_backup.json'
        )
        parser.add_argument(
            '--clear-existing',
            action='store_true',
            help='Clear existing data before loading',
        )

    def handle(self, *args, **options):
        fixture_file = options['fixture_file']
        
        if not os.path.exists(fixture_file):
            self.stdout.write(
                self.style.ERROR(f'Fixture file {fixture_file} not found')
            )
            return

        if options['clear_existing']:
            self.stdout.write('Clearing existing data...')
            # Add your data clearing logic here if needed
            # Be careful with this in production!
            
        self.stdout.write(f'Loading data from {fixture_file}...')
        
        try:
            call_command('loaddata', fixture_file)
            self.stdout.write(
                self.style.SUCCESS(f'Successfully loaded data from {fixture_file}')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error loading data: {str(e)}')
            )
