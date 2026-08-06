FROM python:3.12-slim

# boto3 version isn't pinned to the app's: this is only used by init_resources.py
# to talk to the moto server, so it just needs to satisfy moto's own botocore range.
RUN pip install --no-cache-dir "moto[server]==5.2.2" boto3

WORKDIR /app
COPY init_resources.py entrypoint.sh run_server.py /app/
RUN chmod +x /app/entrypoint.sh

EXPOSE 5001

ENTRYPOINT ["/app/entrypoint.sh"]
