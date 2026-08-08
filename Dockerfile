# Stage 1: Base build stage
FROM python:3.14-slim AS builder

# Create app directory
RUN mkdir /app

# Set working directory
WORKDIR /app

# Set environment variables
# Prevents Python from writing pyc files to disk
ENV PYTHONDONTWRITEBYETCODE=1
#Prevents Python from buffering stdout and stderr
ENV PYTHONUNBUFFERED=1

# Upgrade pip
RUN pip install --upgrade pip

# Which dependency set to install. The web service takes the default; the Celery
# worker overrides it with requirements/worker.txt to add the event-processing
# deps. Same base layers for both.
ARG REQUIREMENTS=requirements/base.txt

COPY requirements/ /app/requirements/

# Install python dependencies
RUN pip install --no-cache-dir -r ${REQUIREMENTS}

# Stage 2: Production stage
FROM python:3.14-slim

RUN useradd -m -r appuser && \
    mkdir /app && \
    chown -R appuser /app

# Copy the Python dependencies from the builder stage
COPY --from=builder /usr/local/lib/python3.14/site-packages/ /usr/local/lib/python3.14/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Set working directory
WORKDIR /app

# Copy the application code
COPY --chown=appuser:appuser . .

# Set environment variables to optimize Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN chmod +x runserver.sh

USER appuser

EXPOSE 8000
CMD ["./runserver.sh"]