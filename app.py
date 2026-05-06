import threading
from datetime import datetime
from flask import Flask, render_template, Response, request
from flask_socketio import SocketIO, disconnect as _disconnect

try:
    from Robo import Robot
    robo = Robot()
except Exception as e:
    print(f"[WARN] Robot unavailable: {e}")
    robo = None

try:
    from picamera2 import Picamera2
    import cv2
    _cam_available = True
except Exception:
    _cam_available = False
    print("[WARN] Camera unavailable")

app = Flask(__name__)
app.config['SECRET_KEY'] = 'raspcar_secret'
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins='*')

MOVE_SPEED = 0.3
TURN_SPEED = 0.4

connections = {}          # {sid: {ip, connected_at, last_cmd}}
active_controller = None  # sid of client with control, or None
_lock = threading.Lock()

_camera_frame = None
_frame_cond = threading.Condition()


# ── Camera ──────────────────────────────────────────────────────────────────

def _camera_loop():
    global _camera_frame
    picam2 = Picamera2()
    cfg = picam2.create_video_configuration(main={"size": (640, 480), "format": "RGB888"})
    picam2.configure(cfg)
    picam2.start()
    try:
        while True:
            arr = picam2.capture_array()
            arr = cv2.rotate(arr, cv2.ROTATE_180)
            _, jpg = cv2.imencode('.jpg', arr, [cv2.IMWRITE_JPEG_QUALITY, 85])
            with _frame_cond:
                _camera_frame = jpg.tobytes()
                _frame_cond.notify_all()
    finally:
        picam2.stop()


def _gen_frames():
    while True:
        with _frame_cond:
            _frame_cond.wait(timeout=2.0)
            frame = _camera_frame
        if frame:
            yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'


# ── Helpers ──────────────────────────────────────────────────────────────────

def _snapshot():
    """Return serialisable connection list. Call while holding _lock."""
    return {
        'active_controller': active_controller,
        'connections': [
            {
                'sid': sid,
                'ip': info['ip'],
                'connected_at': info['connected_at'],
                'last_cmd': info['last_cmd'],
                'is_controller': sid == active_controller,
            }
            for sid, info in connections.items()
        ],
    }


def _broadcast(data):
    socketio.emit('connection_list', data)


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/video_feed')
def video_feed():
    if not _cam_available:
        return Response('Camera unavailable', status=503)
    return Response(_gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


# ── SocketIO events ───────────────────────────────────────────────────────────

@socketio.on('connect')
def on_connect():
    sid = request.sid
    with _lock:
        connections[sid] = {
            'ip': request.remote_addr,
            'connected_at': datetime.now().strftime('%H:%M:%S'),
            'last_cmd': '—',
        }
        data = _snapshot()
    _broadcast(data)


@socketio.on('disconnect')
def on_disconnect():
    global active_controller
    sid = request.sid
    with _lock:
        connections.pop(sid, None)
        if active_controller == sid:
            active_controller = None
            if robo:
                robo.stop()
        data = _snapshot()
    _broadcast(data)


@socketio.on('take_control')
def on_take_control():
    global active_controller
    sid = request.sid
    with _lock:
        if active_controller is None:
            active_controller = sid
            data = _snapshot()
        else:
            data = None
    if data:
        _broadcast(data)


@socketio.on('release_control')
def on_release_control():
    global active_controller
    sid = request.sid
    with _lock:
        if active_controller == sid:
            active_controller = None
            if robo:
                robo.stop()
            data = _snapshot()
        else:
            data = None
    if data:
        _broadcast(data)


_CMD_SPEED = {'F': MOVE_SPEED, 'B': MOVE_SPEED, 'L': TURN_SPEED, 'R': TURN_SPEED}
_CMD_METHOD = {'F': 'forward', 'B': 'backward', 'L': 'left', 'R': 'right', 'S': 'stop'}


@socketio.on('command')
def on_command(data):
    sid = request.sid
    direction = data.get('dir', 'S')
    if direction not in _CMD_METHOD:
        return
    with _lock:
        if sid != active_controller:
            return
        if robo:
            method = getattr(robo, _CMD_METHOD[direction])
            if direction == 'S':
                method()
            else:
                method(_CMD_SPEED[direction])
        if sid in connections:
            connections[sid]['last_cmd'] = direction
        snap = _snapshot()
    _broadcast(snap)


@socketio.on('drop_client')
def on_drop(data):
    target = data.get('sid', '')
    if target and target in connections:
        socketio.disconnect(target, namespace='/')


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if _cam_available:
        threading.Thread(target=_camera_loop, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
