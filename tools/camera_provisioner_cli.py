import argparse
import requests

PROVISION_ENDPOINT = 'http://localhost:8000/v1/cameras/provision/'
def provision_camera(device_id: str):
    payload = {'device_id': device_id}
    headers = {'Content-Type': 'application/json'}
    response = requests.post(PROVISION_ENDPOINT, json=payload, headers=headers, timeout=10)
    if response.status_code == 201:
        print('Camera Provisioned Successfully')
        print(response.json())
    else:
        print('Camera Provisioned Failed')
        print(f'Response Status Code: {response.status_code}')
        print(response.json())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--device_id', type=str, required=True)
    args = parser.parse_args()
    provision_camera(device_id=args.device_id)
