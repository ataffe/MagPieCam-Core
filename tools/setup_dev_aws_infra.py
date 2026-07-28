import sys

import boto3
import argparse
import requests
import json

S3_DETECTION_BUCKET_NAME = 'scout-cam-detection-images-dev'
S3_PREVIEW_BUCKET_NAME = 'scout-cam-preview-images-dev'
SQS_QUEUE_NAME = 'scout-cam-image-queue-dev'

def create_s3_bucket(bucket_name, port, queue_arn = None, include_sqs_notifications=False):
    s3 = boto3.resource(
        's3',
        region_name='us-west-1',
        endpoint_url=f'http://localhost:{port}',
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
    return bucket

def create_sqs_queue(queue_name, port):
    sqs = boto3.resource('sqs',
                       region_name='us-west-1',
                       endpoint_url=f'http://localhost:{port}',
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

def test_system(image_queue, s3_detection_image_bucket):
    print(f'{"="*5} Starting system test.{"="*5}')
    s3_detection_image_bucket.put_object(Key='test', Body=b'test')
    messages = image_queue.receive_messages(MaxNumberOfMessages=2, WaitTimeSeconds=5)
    assert len(messages) > 0, f'Expected 2 messages, but got {len(messages)}'
    for message in messages:
        message.delete()
    print(f'Found {len(messages)} messages.')
    print(f'{"="*5}System test passed!{"="*5}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser('A script to set up AWS services on a dev machine running a moto sever for testing.')
    parser.add_argument('--reset', action='store_true', help='Reset all AWS services.')
    parser.add_argument('--moto-port', type=int, help='Moto port to use.', default=3000)
    args = parser.parse_args()

    if args.reset:
        requests.post("http://localhost:3000/moto-api/reset")
        print(f'Reset all AWS services!')

    queue, image_queue_arn = create_sqs_queue(SQS_QUEUE_NAME, args.moto_port)
    s3_bucket = create_s3_bucket(
        bucket_name=S3_DETECTION_BUCKET_NAME,
        port=args.moto_port,
        queue_arn=image_queue_arn,
        include_sqs_notifications=True)

    s3_bucket = create_s3_bucket(
        bucket_name=S3_PREVIEW_BUCKET_NAME,
        port=args.moto_port)

    test_system(queue, s3_bucket)
