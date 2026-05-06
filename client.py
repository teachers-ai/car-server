"""
RasCar client — run on any machine on the same network.
Controls the car via keyboard using arrow keys.

Install deps:  pip install python-socketio requests
Run:           python client.py
"""

import socketio
import curses
import threading
import time

SERVER = 'http://192.168.12.147:5000'

sio = socketio.Client()
state = {
    'connected': False,
    'i_am_controller': False,
    'active_controller': None,
    'connections': [],
    'last_cmd': '—',
    'move_speed': 0.3,
    'turn_speed': 0.4,
}

# ── Socket.IO events ──────────────────────────────────────────────────────────

@sio.on('connect')
def on_connect():
    state['connected'] = True
    sio.emit('take_control')

@sio.on('disconnect')
def on_disconnect():
    state['connected'] = False
    state['i_am_controller'] = False

@sio.on('connection_list')
def on_list(data):
    state['active_controller'] = data.get('active_controller')
    state['connections'] = data.get('connections', [])
    state['i_am_controller'] = (state['active_controller'] == sio.sid)

@sio.on('speed_update')
def on_speed(data):
    state['move_speed'] = data.get('move_speed', state['move_speed'])
    state['turn_speed'] = data.get('turn_speed', state['turn_speed'])

# ── Car commands ──────────────────────────────────────────────────────────────

def send(direction):
    if state['i_am_controller']:
        sio.emit('command', {'dir': direction})
        state['last_cmd'] = direction

def stop():
    send('S')

# ── Curses UI ─────────────────────────────────────────────────────────────────

KEY_MAP = {
    curses.KEY_UP:    'F',
    curses.KEY_DOWN:  'B',
    curses.KEY_LEFT:  'L',
    curses.KEY_RIGHT: 'R',
}

CMD_LABEL = {'F': 'FORWARD', 'B': 'BACKWARD', 'L': 'LEFT', 'R': 'RIGHT', 'S': 'STOP', '—': '—'}

def draw(scr):
    scr.clear()
    h, w = scr.getmaxyx()

    def put(row, col, text, attr=0):
        try:
            scr.addstr(row, col, text, attr)
        except curses.error:
            pass

    bold  = curses.A_BOLD
    rev   = curses.A_REVERSE

    put(0, 0, '─' * w)
    put(1, 2, 'RasCar FPV Client', bold)
    put(2, 0, '─' * w)

    # Connection
    conn_str = f"Server : {SERVER}"
    status   = "CONNECTED" if state['connected'] else "DISCONNECTED"
    put(3, 2, conn_str)
    attr = bold if state['connected'] else 0
    put(4, 2, f"Status : {status}", attr)

    # Control
    ctrl = state['active_controller']
    if not ctrl:
        ctrl_str = "Control: FREE"
    elif state['i_am_controller']:
        ctrl_str = "Control: YOU  ✓"
    else:
        ctrl_str = f"Control: OTHER ({len(state['connections'])} clients)"
    put(5, 2, ctrl_str, bold if state['i_am_controller'] else 0)

    # Speed
    put(6, 2, f"Speed  : move={state['move_speed']:.2f}  turn={state['turn_speed']:.2f}")

    # Last command
    put(7, 2, f"Command: {CMD_LABEL.get(state['last_cmd'], state['last_cmd'])}", bold)

    put(8, 0, '─' * w)

    # D-pad diagram
    pad = [
        "        [ ↑ FWD ]        ",
        "  [ ← LEFT ]  [ → RIGHT ]",
        "        [ ↓ BACK ]       ",
    ]
    for i, line in enumerate(pad):
        put(10 + i, 2, line)

    put(14, 0, '─' * w)
    put(15, 2, "Keys: Arrow keys = drive  |  S = stop  |  T = take control  |  Q = quit")
    put(16, 0, '─' * w)

    scr.refresh()


def run(scr):
    curses.curs_set(0)
    scr.nodelay(True)
    scr.keypad(True)

    held = False

    while True:
        draw(scr)
        key = scr.getch()

        if key == ord('q') or key == ord('Q'):
            stop()
            break

        if key == ord('t') or key == ord('T'):
            sio.emit('take_control')

        if key == ord('s') or key == ord('S'):
            stop()
            held = False

        direction = KEY_MAP.get(key)
        if direction:
            send(direction)
            held = True
        elif held and key == -1:
            # No key pressed — stop if we were moving
            stop()
            held = False

        time.sleep(0.05)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print(f'Connecting to {SERVER} ...')
    try:
        sio.connect(SERVER, transports=['polling'])
    except Exception as e:
        print(f'Connection failed: {e}')
        exit(1)

    print('Connected. Starting UI...')
    time.sleep(0.5)

    try:
        curses.wrapper(run)
    finally:
        stop()
        sio.disconnect()
        print('Disconnected.')
