"""Creates the S3 buckets and SQS queue the app expects against a freshly
started moto server. Moto keeps no state across restarts, so this needs to
run every time the container starts.
"""
import os
import sys
import time
import json

import boto3
from botocore.exceptions import BotoCoreError, ClientError

MOTO_PORT = os.environ.get("MOTO_PORT")
ENDPOINT_URL = f"http://localhost:{MOTO_PORT}"
REGION = os.environ.get("AWS_REGION", "us-west-1")

DETECTION_BUCKET = os.environ.get("AWS_IMG_DETECTION_BUCKET")
PREVIEW_BUCKET = os.environ.get("AWS_IMG_PREVIEW_BUCKET")
QUEUE_NAME = os.environ.get("SQS_QUEUE_NAME")


def wait_for_moto(timeout_seconds=40):
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


def create_s3_bucket(bucket_name, queue_arn = None, include_sqs_notifications=False):
    s3 = boto3.resource(
        's3',
        region_name=REGION,
        endpoint_url=ENDPOINT_URL,
        aws_access_key_id='test',
        aws_secret_access_key='test')

    bucket = s3.Bucket(bucket_name)
    bucket.create(Bucket=bucket_name,
                     CreateBucketConfiguration={'LocationConstraint': 'us-west-1'})
    print(f'Created S3 Bucket: {bucket.name}')
    if include_sqs_notifications:
        bucket_notification = s3.BucketNotification(bucket_name)
        bucket_notification.put(
            NotificationConfiguration={
                'QueueConfigurations': [{
                    'QueueArn': queue_arn,
                    'Events': ['s3:ObjectCreated:*'],
                }]
            }
        )
        print(f'Created bucket notification for S3 Bucket: {bucket.name}')


def create_sqs_queue(queue_name):
    sqs = boto3.resource('sqs',
                       region_name=REGION,
                       endpoint_url=ENDPOINT_URL,
                       aws_access_key_id='test',
                       aws_secret_access_key='test')

    dlq = sqs.create_queue(QueueName=f'{queue_name}-dlq')
    dlq_url = dlq.url
    dlq_arn = dlq.attributes.get('QueueArn')
    print(f'Created SQS Queue: {dlq_url} | ARN: {dlq_arn}')

    image_queue = sqs.create_queue(QueueName=queue_name,
                              Attributes={
                                  'RedrivePolicy': json.dumps({
                                      'deadLetterTargetArn': dlq_arn,
                                      'maxReceiveCount': 10, # move to DLQ after 3 failed receive attempts
                                      'MessageRetentionPeriod': 3600,
                                  })
                              })
    image_queue_url = image_queue.url
    image_queue_arn = image_queue.attributes.get('QueueArn')
    print(f'Created SQS Queue: {image_queue_url} | ARN: {image_queue_arn}')
    poicly_res = image_queue.set_attributes(
                             Attributes={
                                 'Policy': json.dumps({
                                     "Version": "2012-10-17",
                                     "Statement": [{
                                         "Effect": "Allow",
                                         "Principal": {"Service": "s3.amazonaws.com"},
                                         "Action": "sqs:SendMessage",
                                         "Resource": image_queue_arn,
                                         "Condition": {
                                             "ArnLike": {
                                                 "aws:SourceArn": "arn:aws:s3:::scout-cam-images-dev"
                                             }
                                         }
                                     }]
                                 })
                             })
    if poicly_res:
        print(f'Set Queue Policy.')
    return image_queue, image_queue_arn

if __name__ == "__main__":
    wait_for_moto()
    queue, image_queue_arn = create_sqs_queue(QUEUE_NAME)
    create_s3_bucket(
        bucket_name=DETECTION_BUCKET,
        queue_arn=image_queue_arn,
        include_sqs_notifications=True)

    create_s3_bucket(
        bucket_name=PREVIEW_BUCKET)