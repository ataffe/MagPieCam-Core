"""Seeds the S3 buckets and SQS queue the app expects against a freshly
started moto server. Moto keeps no state across restarts, so this needs to
run every time the container starts.
"""
import os
import sys
import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError

ENDPOINT_URL = "http://localhost:5000"
REGION = os.environ.get("AWS_REGION", "us-west-1")

BUCKETS = [
    bucket
    for bucket in (
        os.environ.get("AWS_IMG_DETECTION_BUCKET"),
        os.environ.get("AWS_IMG_PREVIEW_BUCKET"),
    )
    if bucket
]
QUEUE_NAME = os.environ.get("SQS_QUEUE_NAME")


def wait_for_moto(timeout_seconds=30):
    client = boto3.client("s3", endpoint_url=ENDPOINT_URL, region_name=REGION)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            client.list_buckets()
            return
        except (BotoCoreError, ClientError):
            time.sleep(0.5)
    print("moto server did not become ready in time", file=sys.stderr)
    sys.exit(1)


def create_buckets():
    s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL, region_name=REGION)
    for bucket in BUCKETS:
        kwargs = {}
        if REGION != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": REGION}
        s3.create_bucket(Bucket=bucket, **kwargs)
        print(f"created bucket {bucket}")


def create_queue():
    if not QUEUE_NAME:
        return
    sqs = boto3.client("sqs", endpoint_url=ENDPOINT_URL, region_name=REGION)
    sqs.create_queue(QueueName=QUEUE_NAME)
    print(f"created queue {QUEUE_NAME}")


if __name__ == "__main__":
    wait_for_moto()
    create_buckets()
    create_queue()
