web: python manage.py migrate && python manage.py collectstatic --noinput && gunicorn dandi_sql.wsgi:application --bind 0.0.0.0:$PORT
