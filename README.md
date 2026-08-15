# MagPieCam-Core

A scalable web service built using Django for managing users, cameras, and rules etc. for the scout notification camera system.
This web service handles registering / logging in users, and CRUD operations for users, cameras and rules for cameras. It also serves presigned urls to the Scout camera client for uploading images to AWS S3.
All endpoints are secured using JWTs and the service is currently designed to be used with postgres version 18+ because it uses the
UUIDv7 function.

## System Diagram
![MagPieCam System Diagram](https://github.com/ataffe/MagPieCam-Assets/blob/main/system_diagram/magpie-cam-system-diagram-core.png?raw=true)

### Brief Overview

[MagPieCam Edge Agent](https://github.com/ataffe/MagPieCamEdgeAgent) - An agent that runs on the camera. It tracks movement and sends images and video to the 
MagPieCam-Core backend for processing.

[MagPieCam-iOS](https://github.com/ataffe/MagPieCam-iOS) - An iOS app that enables users to receive smart notifications
based on rules that they set, and video live video from a MagPieCam.

---

### Building & Starting MagPieCam-Core
Build and start all containers: `docker compose --env-file <env_file> up -d --build`

Build a single image and start container: `docker compose --env-file <env_file> up -d --build <container_name>`

Restart container - `docker compose --env-file <env_file> up -d --no-deps <container_name>`