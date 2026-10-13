# Base image
FROM python:3.10-slim

# Environment variables to optimize Python execution
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Working directory inside the container
WORKDIR /app

# Copy requirements file and install dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of the application
COPY . /app/

# Expose port 8000 for Django
EXPOSE 8000
ENV PORT=8000

# Run Django behind a production WSGI server. Render provides PORT at runtime.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn strava_analytics.wsgi:application --bind 0.0.0.0:${PORT:-8000}"]
