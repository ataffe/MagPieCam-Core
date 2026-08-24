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

# Which dependency set to install.
# Base = base requirements for all containers
# API = requirements for the api version of the rules model
# hosted = requirements for the hosted version of the rules model
ARG REQUIREMENTS=requirements/api.txt

COPY requirements/ /app/requirements/

# Install python dependencies
RUN pip install --no-cache-dir -r ${REQUIREMENTS}

# Stage 2: Production stage
FROM python:3.14-slim

# The hosted ML worker JIT-compiles Triton kernels at runtime (torch's _native
# eager ops), which needs a C compiler present in the running container.
# Enabled only for the ML image via build arg.
ARG INSTALL_ML_BUILD_TOOLS=0
RUN if [ "$INSTALL_ML_BUILD_TOOLS" = "1" ]; then \
        apt-get update && \
        apt-get install -y --no-install-recommends gcc libc6-dev && \
        rm -rf /var/lib/apt/lists/*; \
    fi

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

# ml_weights download directory
RUN mkdir -p /app/ml_weights && chown appuser:appuser /app/ml_weights

# Directory for prometheus metrics aggreagation across multiple processes.
RUN mkdir -p /tmp/prometheus_multiproc && chown appuser:appuser /tmp/prometheus_multiproc

# Environment variables to optimize Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc

RUN chmod +x runserver.sh

USER appuser

# Django port
EXPOSE 8000
# Rules eval worker prometheus metrics port
EXPOSE 8225
CMD ["./runserver.sh"]