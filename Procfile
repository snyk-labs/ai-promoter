web: gunicorn "app:create_app()"
worker: celery -A make_celery.celery worker -l INFO
beat: celery -A make_celery.celery beat -l INFO
release: FLASK_APP=app.py flask db upgrade 