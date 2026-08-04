# ScoutCam Web Service

A scalable web service built using Django for managing users, cameras, and rules etc. for the scout notification camera system.
This web service handles registering / logging in users, and CRUD operations for users, cameras and rules for cameras. It also serves presigned urls to the Scout camera client for uploading images to AWS S3.
All endpoints are secured using JWTs and the service is currently designed to be used with postgres version 18+ because it uses the
UUIDv7 function.

## System Diagram
![Scout Cam System Diagram](https://github.com/ataffe/ScoutCamAssets/blob/main/system_diagram/scout-cam-system-diagram-web-service.png?raw=true)

### Brief Overview

[Scout Cam Camera Client](https://github.com/ataffe/GuardianCamCameraClient) - Detects Motion and filters images using object detection and then sends the image to the 
event processor if an object is detected.

[Scout Cam iOS App](https://github.com/ataffe/ScoutCamiOS) - User app for managing cameras and notifying the user of events.

---

### Building & Starting the Web Service
Build and start all containers: `docker compose --env-file <env_file> up -d --build`

Build a single image and start container: `docker compose --env-file <env_file> up -d --build <container_name>`

Restart container - `docker compose --env-file <env_file> up -d --no-deps <container_name>`