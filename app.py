from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import sys
import os

# Add parent directory to path to import original f1_data module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'f1-race-replay'))

from src.f1_data import get_race_telemetry, enable_cache, load_session, list_rounds
import threading
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'f1-race-replay-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global state for race replay
current_replay = {
    'session': None,
    'telemetry': None,
    'frame_index': 0,
    'is_playing': False,
    'speed': 1.0,
    'total_frames': 0
}

@app.route('/')
def index():
    """Main page with race selection"""
    return render_template('index.html')

@app.route('/viewer')
def viewer():
    """Race replay viewer page"""
    return render_template('viewer.html')

@app.route('/api/years')
def get_years():
    """Get available F1 years"""
    return jsonify([2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025])

@app.route('/api/rounds/<int:year>')
def get_rounds(year):
    """Get available rounds for a year"""
    try:
        rounds = list_rounds(year)
        return jsonify(rounds)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/load_race', methods=['POST'])
def load_race():
    """Load race data"""
    try:
        data = request.json
        year = data.get('year')
        round_number = data.get('round')
        session_type = data.get('session_type', 'R')
        
        print(f"Loading F1 {year} Round {round_number} Session '{session_type}'")
        
        # Enable FastF1 cache
        enable_cache()
        
        # Load session
        session = load_session(year, round_number, session_type)
        
        # Get telemetry data
        telemetry = get_race_telemetry(session, session_type=session_type)
        
        # Store in global state
        current_replay['session'] = session
        current_replay['telemetry'] = telemetry
        current_replay['frame_index'] = 0
        current_replay['total_frames'] = telemetry['total_frames']
        current_replay['is_playing'] = False
        
        # Return race info
        return jsonify({
            'success': True,
            'event_name': session.event['EventName'],
            'round_number': session.event['RoundNumber'],
            'total_frames': telemetry['total_frames'],
            'drivers': [
                {
                    'number': d['driver_number'],
                    'code': d['driver_code'],
                    'color': d['team_color']
                }
                for d in telemetry['drivers_info']
            ]
        })
        
    except Exception as e:
        print(f"Error loading race: {e}")
        return jsonify({'error': str(e)}), 500

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print('Client connected')
    emit('status', {'message': 'Connected to F1 Race Replay server'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print('Client disconnected')

@socketio.on('play')
def handle_play():
    """Start race replay"""
    current_replay['is_playing'] = True
    threading.Thread(target=replay_loop, daemon=True).start()

@socketio.on('pause')
def handle_pause():
    """Pause race replay"""
    current_replay['is_playing'] = False

@socketio.on('seek')
def handle_seek(data):
    """Seek to specific frame"""
    frame = data.get('frame', 0)
    current_replay['frame_index'] = min(frame, current_replay['total_frames'] - 1)
    emit_current_frame()

@socketio.on('set_speed')
def handle_set_speed(data):
    """Set playback speed"""
    speed = data.get('speed', 1.0)
    current_replay['speed'] = max(0.25, min(4.0, speed))

def emit_current_frame():
    """Emit current frame data to all clients"""
    if current_replay['telemetry'] is None:
        return
    
    frame_idx = current_replay['frame_index']
    telemetry = current_replay['telemetry']
    
    # Get frame data for all drivers
    frame_data = {
        'frame': frame_idx,
        'total_frames': telemetry['total_frames'],
        'time': telemetry['time_s'][frame_idx] if frame_idx < len(telemetry['time_s']) else 0,
        'drivers': []
    }
    
    for driver in telemetry['drivers_info']:
        driver_idx = driver['index']
        driver_data = telemetry['drivers_data'][driver_idx]
        
        if frame_idx < len(driver_data['x']):
            frame_data['drivers'].append({
                'number': driver['driver_number'],
                'code': driver['driver_code'],
                'color': driver['team_color'],
                'x': float(driver_data['x'][frame_idx]),
                'y': float(driver_data['y'][frame_idx]),
                'speed': float(driver_data['speed_kph'][frame_idx]),
                'lap': int(driver_data['lap_number'][frame_idx]),
                'position': int(driver_data['position'][frame_idx]) if frame_idx < len(driver_data['position']) else 0,
                'tyre': int(driver_data['tyre_compound'][frame_idx]),
                'is_out': bool(driver_data['is_out'][frame_idx])
            })
    
    socketio.emit('frame_update', frame_data)

def replay_loop():
    """Main replay loop - runs in background thread"""
    while current_replay['is_playing'] and current_replay['telemetry'] is not None:
        # Emit current frame
        emit_current_frame()
        
        # Advance frame
        current_replay['frame_index'] += 1
        
        # Check if reached end
        if current_replay['frame_index'] >= current_replay['total_frames']:
            current_replay['is_playing'] = False
            current_replay['frame_index'] = 0
            socketio.emit('replay_ended', {})
            break
        
        # Sleep based on speed (25 FPS base)
        time.sleep((1/25) / current_replay['speed'])

if __name__ == '__main__':
    # Enable FastF1 cache on startup
    enable_cache()
    
    # Get port from environment
    port = int(os.environ.get('PORT', 5000))
    
    # Run with SocketIO
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
