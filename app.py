from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import sys
import os

# Add parent directory to path to import original f1_data module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'f1-race-replay'))

from src.f1_data import get_race_telemetry, enable_cache, load_session
import fastf1
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

@app.route('/api/status')
def get_status():
    """Get current replay status for debugging"""
    return jsonify({
        'has_session': current_replay.get('session') is not None,
        'has_frames': current_replay.get('frames') is not None,
        'total_frames': current_replay.get('total_frames', 0),
        'current_frame': current_replay.get('frame_index', 0),
        'is_playing': current_replay.get('is_playing', False),
        'frame_count': len(current_replay.get('frames', []))
    })

@app.route('/api/test_emit')
def test_emit():
    """Test emitting a single frame"""
    try:
        print("🧪 TEST: Manually emitting current frame")
        emit_current_frame()
        return jsonify({'success': True, 'message': 'Frame emitted'})
    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

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
        enable_cache()
        schedule = fastf1.get_event_schedule(year)
        rounds = []
        for _, event in schedule.iterrows():
            rounds.append({
                'round': int(event['RoundNumber']),
                'name': str(event['EventName']),
                'location': str(event['Location']) if 'Location' in event else str(event['Country'])
            })
        return jsonify(rounds)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/load_race', methods=['POST'])
def load_race():
    """Load race data"""
    try:
        data = request.json
        year = int(data.get('year'))
        round_number = int(data.get('round'))
        session_type = data.get('session_type', 'R')
        
        print(f"Loading F1 {year} Round {round_number} Session '{session_type}'")
        
        # Validate session type exists for this event
        if session_type == 'S':
            # Check if sprint exists
            enable_cache()
            event = fastf1.get_event(year, round_number)
            if 'Sprint' not in str(event.get_session_name(session_type)):
                return jsonify({'error': 'Sprint session does not exist for this race weekend. Try Race (R) or Qualifying (Q) instead.'}), 400
        
        # Enable FastF1 cache
        enable_cache()
        
        # Load session
        session = load_session(year, round_number, session_type)
        
        # Get telemetry data (this is the slow part!)
        print("⏳ Getting race telemetry... this may take 30-60 seconds")
        import time
        start_time = time.time()
        
        telemetry = get_race_telemetry(session, session_type=session_type)
        
        elapsed = time.time() - start_time
        print(f"✅ Telemetry loaded in {elapsed:.1f} seconds")
        
        # Extract frames and calculate total
        frames = telemetry.get('frames', [])
        
        # TEMP FIX: Limit to first 10 minutes to prevent memory overload
        # 25 FPS * 60 sec * 10 min = 15,000 frames max
        max_frames = 15000
        if len(frames) > max_frames:
            print(f"⚠️ Limiting frames: {len(frames)} → {max_frames} (first 10 minutes)")
            frames = frames[:max_frames]
        
        total_frames = len(frames)
        
        # Store in global state
        current_replay['session'] = session
        current_replay['telemetry'] = telemetry
        current_replay['frames'] = frames
        current_replay['frame_index'] = 0
        current_replay['total_frames'] = total_frames
        current_replay['is_playing'] = False
        
        # Get total laps if available
        total_laps = telemetry.get('total_laps', 0)
        
        # Emit first frame to show initial state
        socketio.emit('initial_load_complete', {
            'total_frames': total_frames,
            'event_name': str(session.event['EventName']),
            'total_laps': int(total_laps) if total_laps else 0
        })
        
        # Get driver info from first frame
        drivers_info = []
        if frames and len(frames) > 0 and 'drivers' in frames[0]:
            first_frame_drivers = frames[0]['drivers']
            driver_colors = telemetry.get('driver_colors', {})
            
            for driver_code in first_frame_drivers.keys():
                color = driver_colors.get(driver_code, (128, 128, 128))
                # Convert RGB tuple to hex
                hex_color = '#{:02x}{:02x}{:02x}'.format(*color)
                drivers_info.append({
                    'code': driver_code,
                    'color': hex_color
                })
        
        # Return race info
        return jsonify({
            'success': True,
            'event_name': str(session.event['EventName']),
            'round_number': int(session.event['RoundNumber']),
            'total_frames': int(total_frames),
            'drivers': drivers_info
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
    print("=" * 50)
    print("▶️ PLAY REQUESTED")
    print(f"   Frames loaded: {len(current_replay.get('frames', []))}")
    print(f"   Total frames: {current_replay.get('total_frames', 0)}")
    print(f"   Current index: {current_replay.get('frame_index', 0)}")
    print(f"   Already playing: {current_replay.get('is_playing', False)}")
    
    if not current_replay.get('frames'):
        print("❌ ERROR: No frames loaded!")
        socketio.emit('error', {'message': 'No race data loaded'})
        return
    
    if current_replay.get('is_playing'):
        print("⚠️ Already playing, ignoring")
        return
    
    current_replay['is_playing'] = True
    print("🚀 Starting replay thread...")
    
    try:
        thread = threading.Thread(target=replay_loop, daemon=True)
        thread.start()
        print("✅ Replay thread started successfully")
        print("=" * 50)
    except Exception as e:
        print(f"❌ Failed to start thread: {e}")
        import traceback
        traceback.print_exc()

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
    try:
        frames = current_replay.get('frames')
        if not frames:
            print("⚠️ No frames available")
            return
        
        frame_idx = current_replay['frame_index']
        total_frames = current_replay['total_frames']
        driver_colors = current_replay['telemetry'].get('driver_colors', {})
        
        if frame_idx >= len(frames):
            print(f"⚠️ Frame index {frame_idx} out of range")
            return
        
        frame = frames[frame_idx]
    except Exception as e:
        print(f"❌ Error getting frame: {e}")
        return
    
    # Build driver data from frame
    drivers_list = []
    for driver_code, driver_frame_data in frame.get('drivers', {}).items():
        color = driver_colors.get(driver_code, (128, 128, 128))
        hex_color = '#{:02x}{:02x}{:02x}'.format(*color)
        
        drivers_list.append({
            'code': str(driver_code),
            'color': hex_color,
            'x': float(driver_frame_data.get('x', 0)),
            'y': float(driver_frame_data.get('y', 0)),
            'speed': float(driver_frame_data.get('speed_kph', 0)),
            'lap': int(driver_frame_data.get('lap_number', 1)),
            'position': int(driver_frame_data.get('position', 0)),
            'tyre': int(driver_frame_data.get('tyre_compound', 0)),
            'is_out': bool(driver_frame_data.get('is_out', False))
        })
    
    frame_data = {
        'frame': int(frame_idx),
        'total_frames': int(total_frames),
        'time': float(frame.get('t', 0)),
        'drivers': drivers_list
    }
    
    # Add weather data if available
    if 'weather' in frame:
        weather = frame['weather']
        frame_data['weather'] = {
            'track_temp': float(weather.get('track_temp', 0)) if weather.get('track_temp') else None,
            'air_temp': float(weather.get('air_temp', 0)) if weather.get('air_temp') else None,
            'humidity': float(weather.get('humidity', 0)) if weather.get('humidity') else None,
            'wind_speed': float(weather.get('wind_speed', 0)) if weather.get('wind_speed') else None,
            'rain_state': str(weather.get('rain_state', 'DRY'))
        }
    
    try:
        socketio.emit('frame_update', frame_data)
    except Exception as e:
        print(f"❌ Error emitting frame: {e}")

def replay_loop():
    """Main replay loop - runs in background thread with frame skipping"""
    print("🎬 Replay loop started")
    total = current_replay.get('total_frames', 0)
    print(f"   Total frames: {total}")
    print(f"   Starting from: {current_replay.get('frame_index', 0)}")
    
    # Calculate frame skip to achieve ~5 FPS effective rate
    # Original data is 25 FPS, so skip 4 frames to get 5 FPS
    frame_skip = 5  # 5 FPS effective - balanced speed and data
    print(f"   Frame skip: {frame_skip} (5 FPS - every {frame_skip}th frame)")
    
    frame_count = 0
    
    while current_replay['is_playing'] and current_replay.get('frames'):
        try:
            # Debug: Log before emit
            if frame_count == 0:
                print(f"🎬 About to emit first frame (index {current_replay['frame_index']})")
            
            # Emit current frame
            emit_current_frame()
            frame_count += 1
            
            # Log every frame for first 5, then every 10
            if frame_count <= 5 or frame_count % 10 == 0:
                print(f"📊 Emitted frame #{frame_count}, index: {current_replay['frame_index']}/{total}")
            
            # Advance frame with skipping
            current_replay['frame_index'] += frame_skip
            
            # Check if reached end
            if current_replay['frame_index'] >= total:
                print("🏁 Replay ended")
                current_replay['is_playing'] = False
                current_replay['frame_index'] = 0
                socketio.emit('replay_ended', {})
                break
            
            # Sleep for 5 FPS playback (0.2 seconds per frame)
            sleep_time = (1.0 / 5) / current_replay.get('speed', 1.0)
            time.sleep(sleep_time)
            
        except Exception as e:
            print(f"❌ Error in replay loop: {e}")
            import traceback
            traceback.print_exc()
            break
    
    print(f"🛑 Replay loop exited after emitting {frame_count} frames")

if __name__ == '__main__':
    # Enable FastF1 cache on startup
    enable_cache()
    
    # Get port from environment
    port = int(os.environ.get('PORT', 5000))
    
    # Run with SocketIO
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
