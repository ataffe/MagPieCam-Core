import boto3
import argparse
import json
from urllib.parse import unquote

SQS_QUEUE_NAME = 'scout-cam-image-queue-dev'

def get_queue(queue_name):
    sqs = boto3.resource('sqs',
                         region_name='us-west-1',
                         endpoint_url=f'http://localhost:3000',
                         aws_access_key_id='test',
                         aws_secret_access_key='test')
    return sqs.get_queue_by_name(QueueName=queue_name)

def print_messages(queue, num_messages):
    msgs_consumed = 0
    while msgs_consumed < num_messages:
        messages = queue.receive_messages(MaxNumberOfMessages=num_messages, WaitTimeSeconds=20)
        for message in messages:
            msg_body = json.loads(message.body)
            print(f'{"="*5}Message {msgs_consumed}{"="*5}')
            if 'Records' in msg_body:
                key = msg_body['Records'][0]['s3']['object']['key']
                if key != 'test':
                    msg_body['Records'][0]['s3']['object']['key'] = unquote(key)
            print(json.dumps(msg_body, indent=4))
            message.delete()
            msgs_consumed += 1

if __name__ == '__main__':
    parser = argparse.ArgumentParser('A tool for consuming and viewing SQS messages')
    parser.add_argument('-q', '--queue_name', default=SQS_QUEUE_NAME)
    parser.add_argument('-n', '--num_messages', type=int, default=1)
    args = parser.parse_args()
    print(f'Listening for {args.num_messages} messages')
    print_messages(get_queue(args.queue_name), args.num_messages)
    print('Done')