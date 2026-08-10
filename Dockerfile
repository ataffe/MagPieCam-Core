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

# Which dependency set to install. Defaults to api.txt (base + the event-
# processing runtime) so the one shared image works for the web service, beat,
# the lite worker, and the consumer -- Celery autodiscovery imports events.tasks,
# which pulls in Pillow at module load. The ML worker overrides this with
# hosted.txt to add torch/transformers.
ARG REQUIREMENTS=requirements/api.txt

COPY requirements/ /app/requirements/

# Install python dependencies
RUN pip install --no-cache-dir -r ${REQUIREMENTS}

# Stage 2: Production stage
FROM python:3.14-slim

# The hosted ML worker JIT-compiles Triton kernels at runtime (torch's _native
# eager ops), which needs a C compiler present in the *running* container.
# Enabled only for the ML image via build arg so the shared/lite image stays slim.
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

# ml_weights is .dockerignored, so create it here owned by appuser. A named
# volume mounted at this path on the ML worker inherits that ownership (Docker
# seeds an empty volume from the image mount point), so the model can write the
# downloaded weights as appuser instead of hitting a root-owned mount.
RUN mkdir -p /app/ml_weights && chown appuser:appuser /app/ml_weights

# Set environment variables to optimize Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN chmod +x runserver.sh

USER appuser

EXPOSE 8000
CMD ["./runserver.sh"]