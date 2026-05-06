# RasCar FPV Server

A Flask-based server that runs on a Raspberry Pi car. It streams a live camera feed and accepts remote drive commands over WebSocket, supporting multiple simultaneous connections with a built-in control management UI.

---

## Features

- Live MJPEG camera stream viewable in any browser
- WebSocket-based car control (forward, backward, left, right, stop)
- Exclusive control ownership — only one client drives at a time
- Multi-connection dashboard — see all connected clients in real time
- Drop any connection from the UI

---

## Hardware

- Raspberry Pi (tested on Pi 5)
- OV5647 camera module
- Motor driver with GPIO pins:

| Pin | Role |
|---|---|
| 6 | Left motor direction 1 |
| 12 | Left motor direction 2 |
| 13 | Right motor direction 1 |
| 16 | Right motor direction 2 |
| 20 | Left motor speed (PWM) |
| 21 | Right motor speed (PWM) |

---

## Project Structure

```
car_server/
├── app.py               # Main Flask + Socket.IO server
├── Robo.py              # Motor control via GPIO
├── templates/
│   └── index.html       # Web dashboard UI
├── CLIENT_README.md     # Guide for building a client app
└── requirements.txt     # Python dependencies
```

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/teachers-ai/car-server.git
cd car-server
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install flask flask-socketio picamera2 opencv-python gpiozero
```

### 4. Run the server

```bash
python app.py
```

The server starts on port `5000` and is accessible from any device on the same network.

---

## Usage

Open `http://<pi-ip>:5000` in a browser.

### Dashboard

| Section | Description |
|---|---|
| Camera feed | Live MJPEG stream from the Pi camera |
| Control banner | Shows who currently has control; Take / Release buttons |
| D-pad | Drive buttons — only active when you hold control |
| Connections panel | Lists all connected clients with IP, connect time, last command, and a Drop button |

### Keyboard shortcuts (when you have control)

| Key | Action |
|---|---|
| `↑` | Forward |
| `↓` | Backward |
| `←` | Left |
| `→` | Right |
| `S` | Stop |

Hold a key to keep moving, release to stop.

---

## API

### Camera stream

```
GET /video_feed
```
Returns a `multipart/x-mixed-replace` MJPEG stream. Can be embedded directly in an `<img>` tag or opened in VLC.

### WebSocket events

Connect via Socket.IO to `http://<pi-ip>:5000`.

**Send:**

| Event | Payload | Description |
|---|---|---|
| `take_control` | — | Claim exclusive control of the car |
| `release_control` | — | Release control; car stops |
| `command` | `{"dir": "F\|B\|L\|R\|S"}` | Drive command (only works if you hold control) |
| `drop_client` | `{"sid": "<sid>"}` | Disconnect another client |

**Receive:**

| Event | Payload | Description |
|---|---|---|
| `connection_list` | `{active_controller, connections[]}` | Broadcast to all clients on any state change |

---

## Building a Client App

See [CLIENT_README.md](CLIENT_README.md) for a complete guide on connecting a separate Python or Flask app to this server.

---

## Configuration

Speed values are set in `app.py`:

```python
MOVE_SPEED = 0.3   # forward / backward (0.0 – 1.0)
TURN_SPEED = 0.4   # left / right       (0.0 – 1.0)
```
