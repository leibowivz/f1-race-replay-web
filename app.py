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

# Railway configuration
RAILWAY_ENVIRONMENT = os.getenv('RAILWAY_ENVIRONMENT')
CACHE_DIR = os.getenv('CACHE_DIR', '/tmp/.fastf1-cache')
PORT = int(os.getenv('PORT', 5021))

# Event type constants for progress bar markers
EVENT_DNF = "dnf"
EVENT_YELLOW_FLAG = "yellow"
EVENT_SAFETY_CAR = "sc"
EVENT_RED_FLAG = "red"
EVENT_VSC = "vsc"

def extract_race_events(frames, track_statuses, total_laps):
    """Extract race events for progress bar markers"""
    events = []
    if not frames:
        return events
    
    n_frames = len(frames)
    prev_drivers = set()
    sample_rate = 25
    
    for i in range(0, n_frames, sample_rate):
        frame = frames[i]
        drivers_data = frame.get("drivers", {})
        current_drivers = set(drivers_data.keys())
        
        if prev_drivers:
            dnf_drivers = prev_drivers - current_drivers
            for driver_code in dnf_drivers:
                prev_frame = frames[max(0, i - sample_rate)]
                driver_info = prev_frame.get("drivers", {}).get(driver_code, {})
                lap = driver_info.get("lap", "?")
                events.append({
                    "type": EVENT_DNF,
                    "frame": i,
                    "label": driver_code,
                    "lap": lap,
                })
        prev_drivers = current_drivers
    
    for status in track_statuses:
        status_code = str(status.get("status", ""))
        start_time = status.get("start_time", 0)
        end_time = status.get("end_time")
        
        fps = 25
        start_frame = int(start_time * fps)
        end_frame = int(end_time * fps) if end_time else start_frame + 250
        
        if end_frame <= 0:
            continue
        if n_frames > 0:
            end_frame = min(end_frame, n_frames)
        
        event_type = None
        if status_code == "2":
            event_type = EVENT_YELLOW_FLAG
        elif status_code == "4":
            event_type = EVENT_SAFETY_CAR
        elif status_code == "5":
            event_type = EVENT_RED_FLAG
        elif status_code in ("6", "7"):
            event_type = EVENT_VSC
        
        if event_type:
            events.append({
                "type": event_type,
                "frame": start_frame,
                "end_frame": end_frame,
                "label": "",
                "lap": None,
            })
    
    return events

app = Flask(__name__)
app.config['SECRET_KEY'] = 'f1-race-replay-secret'
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
socketio = SocketIO(app, cors_allowed_origins="*")

# Global state for race replay
current_replay = {
    'session': None,
    'telemetry': None,
    'frame_index': 0,
    'is_playing': False,
    'speed': 1.0,
    'total_frames': 0,
    'last_access': time.time()
}

# Memory management settings
MAX_FRAMES_IN_MEMORY = 50000  # Limit to ~50k frames (~500MB max)
CACHE_TIMEOUT_SECONDS = 1800  # Clear cache after 30 min idle

def clean_old_data():
    """Clean up old replay data to free memory"""
    global current_replay
    if current_replay.get('frames'):
        idle_time = time.time() - current_replay.get('last_access', time.time())
        if idle_time > CACHE_TIMEOUT_SECONDS:
            print(f"🧹 Cleaning up old data (idle {idle_time:.0f}s)")
            current_replay['frames'] = None
            current_replay['telemetry'] = None
            current_replay['session'] = None
            import gc
            gc.collect()

@app.route('/')
def index():
    """Main page with race selection - F1 themed"""
    return render_template('index_f1.html')

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
    """Race replay viewer page with mobile support"""
    return render_template('viewer.html')

@app.route('/qualifying')
def qualifying_view():
    """Qualifying results page"""
    return render_template('qualifying.html')

@app.route('/viewer-mobile')
def viewer_mobile():
    """Mobile-optimized viewer page"""
    return render_template('viewer-mobile.html')

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

@app.route('/api/load_qualifying_lap', methods=['POST'])
def load_qualifying_lap():
    """Load a single qualifying lap for replay"""
    try:
        data = request.json
        year = int(data.get('year'))
        round_number = int(data.get('round'))
        driver_code = data.get('driver_code')
        segment = data.get('segment', 'Q3')
        
        print(f"Loading Qualifying lap: {driver_code} {segment} - {year} R{round_number}")
        
        enable_cache()
        session = load_session(year, round_number, 'Q')
        
        from src.f1_data import get_driver_quali_telemetry, get_driver_colors
        
        # Try to load quali telemetry, fallback to Q2 or Q1 if driver didn't reach Q3
        raw_quali_data = None
        actual_segment = segment
        
        for try_segment in [segment, 'Q2', 'Q1']:
            try:
                print(f"Trying to load {driver_code} {try_segment}...")
                raw_quali_data = get_driver_quali_telemetry(session, driver_code, try_segment)
                actual_segment = try_segment
                print(f"✅ Loaded {driver_code} {try_segment}")
                break
            except ValueError as e:
                print(f"⚠️ {try_segment} not available: {e}")
                continue
        
        if not raw_quali_data:
            return jsonify({'error': f'No qualifying data found for {driver_code}'}), 404
        
        # Convert to race-like format
        driver_telemetry = raw_quali_data['driver_telemetry_data']
        
        # Build frames from telemetry
        frames = []
        timeline = driver_telemetry['t']
        for i in range(len(timeline)):
            frame = {
                't': float(timeline[i]),
                'lap': 1,
                'drivers': {
                    driver_code: {
                        'code': driver_code,
                        'x': float(driver_telemetry['x'][i]),
                        'y': float(driver_telemetry['y'][i]),
                        'speed': float(driver_telemetry['speed'][i]),
                        'gear': int(driver_telemetry['gear'][i]),
                        'throttle': float(driver_telemetry['throttle'][i]),
                        'brake': float(driver_telemetry['brake'][i]),
                        'drs': int(driver_telemetry['drs'][i]),
                        'lap': 1,
                        'pos': 1,
                        'position': 1,
                        'tyre': 1,  # Soft (unknown in quali)
                        'tyre_life': 0,
                        'is_out': False
                    }
                }
            }
            frames.append(frame)
        
        # Track data
        track_data = {
            'x': driver_telemetry['x'],
            'y': driver_telemetry['y'],
            'drs': driver_telemetry['drs']
        }
        
        quali_data = {
            'frames': frames,
            'driver_colors': get_driver_colors(session),
            'track_statuses': [],
            'total_laps': 1,
            'track_data': track_data
        }
        
        # Store in global state (same format as race)
        current_replay['session'] = session
        current_replay['telemetry'] = quali_data
        current_replay['frames'] = quali_data.get('frames', [])
        current_replay['frame_index'] = 0
        current_replay['total_frames'] = len(quali_data.get('frames', []))
        current_replay['is_playing'] = False
        current_replay['race_events'] = []
        
        # Track data from the lap
        track_data = quali_data.get('track_data')
        if track_data:
            import numpy as np
            x_center = np.array(track_data['x'])
            y_center = np.array(track_data['y'])
            
            dx = np.gradient(x_center)
            dy = np.gradient(y_center)
            norm = np.sqrt(dx**2 + dy**2)
            norm[norm == 0] = 1.0
            dx /= norm
            dy /= norm
            
            nx = -dy
            ny = dx
            
            track_width = 200
            x_outer = x_center + nx * (track_width / 2)
            y_outer = y_center + ny * (track_width / 2)
            x_inner = x_center - nx * (track_width / 2)
            y_inner = y_center - ny * (track_width / 2)
            
            track_data['x_inner'] = x_inner.tolist()
            track_data['y_inner'] = y_inner.tolist()
            track_data['x_outer'] = x_outer.tolist()
            track_data['y_outer'] = y_outer.tolist()
        
        current_replay['track_data'] = track_data
        current_replay['event_name'] = f"{session.event['EventName']} - {driver_code} {segment}"
        current_replay['circuit_name'] = str(session.event.get('Location', ''))
        current_replay['country'] = str(session.event.get('Country', ''))
        current_replay['year'] = year
        current_replay['round'] = round_number
        current_replay['total_laps'] = 1
        
        print(f"✅ Qualifying lap loaded: {current_replay['total_frames']} frames")
        
        return jsonify({
            'success': True,
            'total_frames': current_replay['total_frames'],
            'driver': driver_code,
            'segment': segment
        })
        
    except Exception as e:
        print(f"Error loading qualifying lap: {e}")
        import traceback
        traceback.print_exc()
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
        
        # Enable FastF1 cache
        enable_cache()
        
        # Load session
        session = load_session(year, round_number, session_type)
        
        # Qualifying uses special results view
        if session_type == 'Q':
            print("📊 Qualifying mode - loading results")
            from src.f1_data import get_qualifying_results, get_driver_colors
            
            quali_results = get_qualifying_results(session)
            
            return jsonify({
                'redirect': '/qualifying',
                'results': quali_results,
                'event_name': str(session.event['EventName'])
            })
        
        # Get telemetry data (this is the slow part!)
        print("⏳ Getting telemetry... this may take 30-60 seconds")
        import time
        start_time = time.time()
        
        # Use race telemetry for all session types (simplified)
        # Qualifying will show all laps as continuous replay
        telemetry = get_race_telemetry(session, session_type=session_type)
        
        elapsed = time.time() - start_time
        print(f"✅ Telemetry loaded in {elapsed:.1f} seconds")
        
        # Extract frames and calculate total
        frames = telemetry.get('frames', [])
        total_frames = len(frames)
        track_statuses = telemetry.get('track_statuses', [])
        
        print(f"📊 Total frames loaded: {total_frames:,}")
        
        # Memory optimization: downsample if too many frames
        if total_frames > MAX_FRAMES_IN_MEMORY:
            downsample_rate = int(total_frames / MAX_FRAMES_IN_MEMORY) + 1
            print(f"⚠️ Too many frames ({total_frames:,}), downsampling by {downsample_rate}x")
            frames = frames[::downsample_rate]
            print(f"✂️ Reduced to {len(frames):,} frames (saves ~{(1-len(frames)/total_frames)*100:.0f}% memory)")
            # Keep original total for progress bar
            original_total = total_frames
        else:
            original_total = total_frames
        
        # Extract race events for progress bar
        race_events = extract_race_events(frames, track_statuses, telemetry.get('total_laps', 0))
        print(f"📋 Race events extracted: {len(race_events)}")
        
        # Store in global state
        current_replay['session'] = session
        current_replay['telemetry'] = telemetry
        current_replay['frames'] = frames
        current_replay['frame_index'] = 0
        current_replay['total_frames'] = len(frames)  # Use downsampled count
        current_replay['original_total'] = original_total  # Keep for display
        current_replay['is_playing'] = False
        current_replay['race_events'] = race_events
        current_replay['last_access'] = time.time()  # Track access time
        
        # Get total laps if available
        total_laps = telemetry.get('total_laps', 0)
        
        # Get track data for drawing (with inner/outer boundaries)
        track_data = None
        try:
            print("📍 Loading track layout from qualifying session...")
            quali_session = load_session(year, round_number, 'Q')
            print(f"   Qualifying session loaded, laps: {len(quali_session.laps) if quali_session else 0}")
            
            if quali_session and len(quali_session.laps) > 0:
                fastest_lap = quali_session.laps.pick_fastest()
                print(f"   Fastest lap found: {fastest_lap is not None}")
                
                if fastest_lap is not None:
                    lap_telemetry = fastest_lap.get_telemetry()
                    print(f"   Telemetry columns: {list(lap_telemetry.columns)}")
                    
                    # Extract track center line
                    x_center = lap_telemetry['X'].to_numpy()
                    y_center = lap_telemetry['Y'].to_numpy()
                    
                    # Calculate track boundaries (200m width)
                    import numpy as np
                    dx = np.gradient(x_center)
                    dy = np.gradient(y_center)
                    norm = np.sqrt(dx**2 + dy**2)
                    norm[norm == 0] = 1.0
                    dx /= norm
                    dy /= norm
                    
                    # Normal vectors (perpendicular)
                    nx = -dy
                    ny = dx
                    
                    track_width = 200  # meters
                    x_outer = x_center + nx * (track_width / 2)
                    y_outer = y_center + ny * (track_width / 2)
                    x_inner = x_center - nx * (track_width / 2)
                    y_inner = y_center - ny * (track_width / 2)
                    
                    track_data = {
                        'x': x_center.tolist(),
                        'y': y_center.tolist(),
                        'x_inner': x_inner.tolist(),
                        'y_inner': y_inner.tolist(),
                        'x_outer': x_outer.tolist(),
                        'y_outer': y_outer.tolist(),
                        'drs': lap_telemetry['DRS'].tolist() if 'DRS' in lap_telemetry else []
                    }
                    print(f"✅ Loaded track layout: {len(track_data['x'])} points with boundaries")
                else:
                    print("⚠️ No fastest lap found")
            else:
                print("⚠️ No laps in qualifying session")
        except Exception as e:
            print(f"❌ Could not load track layout: {e}")
            import traceback
            traceback.print_exc()
        
        # Store track data and event info for later emission
        current_replay['track_data'] = track_data
        current_replay['event_name'] = str(session.event['EventName'])
        current_replay['circuit_name'] = str(session.event.get('Location', session.event.get('Country', '')))
        current_replay['country'] = str(session.event.get('Country', ''))
        current_replay['year'] = int(year)
        current_replay['round'] = int(round_number)
        current_replay['total_laps'] = int(total_laps) if total_laps else 0
        
        print(f"✅ Race loaded and ready. Will emit to client on WebSocket connect.")
        
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
    print('🔌 Client connected via WebSocket')
    clean_old_data()  # Clean up old data on new connection
    current_replay['last_access'] = time.time()
    emit('status', {'message': 'Connected to F1 Race Replay server'})
    
    # Send initial data if race is loaded
    if current_replay.get('frames'):
        print(f"📤 Sending initial_load_complete: {current_replay['total_frames']} frames, event: {current_replay.get('event_name')}")
        emit('initial_load_complete', {
            'total_frames': current_replay['total_frames'],
            'event_name': current_replay.get('event_name', ''),
            'circuit_name': current_replay.get('circuit_name', ''),
            'country': current_replay.get('country', ''),
            'year': current_replay.get('year', 0),
            'round': current_replay.get('round', 0),
            'total_laps': current_replay.get('total_laps', 0),
            'track_data': current_replay.get('track_data'),
            'race_events': current_replay.get('race_events', [])
        })
        print("✅ initial_load_complete emitted")
    else:
        print("⚠️ No race data loaded yet")

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
            'speed': float(driver_frame_data.get('speed', 0)),
            'lap': int(driver_frame_data.get('lap', 1)),
            'position': int(driver_frame_data.get('pos', driver_frame_data.get('position', 0))),
            'tyre': int(driver_frame_data.get('tyre', 0)),
            'tyre_life': float(driver_frame_data.get('tyre_life', 0)),
            'throttle': float(driver_frame_data.get('throttle', 0)),
            'brake': float(driver_frame_data.get('brake', 0)),
            'gear': int(driver_frame_data.get('gear', 0)),
            'drs': int(driver_frame_data.get('drs', 0)),
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
            
            # Slower sleep for cloud deployment to avoid WebSocket buffer buildup
            # Railway has higher latency than local, so we need to slow down
            time.sleep(0.1)  # 100ms between frames = 10 FPS max, front-end limits to 5 FPS
            
        except Exception as e:
            print(f"❌ Error in replay loop: {e}")
            import traceback
            traceback.print_exc()
            break
    
    print(f"🛑 Replay loop exited after emitting {frame_count} frames")

def memory_cleanup_task():
    """Background task to periodically clean up old data"""
    while True:
        time.sleep(300)  # Check every 5 minutes
        clean_old_data()

if __name__ == '__main__':
    # Enable FastF1 cache on startup
    enable_cache()
    print(f"🏎️ Cache directory: {CACHE_DIR}")
    
    # Start memory cleanup thread
    cleanup_thread = threading.Thread(target=memory_cleanup_task, daemon=True)
    cleanup_thread.start()
    print("🧹 Memory cleanup task started (checks every 5 min)")
    
    # Railway environment detection
    if RAILWAY_ENVIRONMENT:
        print(f"🚂 Running on Railway ({RAILWAY_ENVIRONMENT} environment)")
        print(f"⚡ Auto-sleep enabled (5 min inactivity)")
    
    # Get port from environment (Railway uses PORT env var)
    port = int(os.environ.get('PORT', PORT))
    print(f"🌐 Starting server on 0.0.0.0:{port}")
    
    # Run with SocketIO
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)


