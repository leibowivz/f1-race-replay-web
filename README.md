# F1 Race Replay - Web Version 🏎️

A web-based Formula 1 race visualization and replay tool with advanced telemetry, interactive track display, and mobile support.

## Features

### Core Features
- 🏁 **Race Replay**: Watch F1 races with real-time telemetry data
- 🏆 **Qualifying Replay**: View qualifying sessions with single-lap replay
- 🏃 **Sprint Replay**: Support for sprint race sessions
- ⏯️ **Playback Controls**: Play, pause, seek, and adjust speed (0.5x - 4x)
- 🎨 **Visual Track Display**: HTML5 Canvas with team colors and real track layout

### Advanced Telemetry
- 📊 **Driver Telemetry**: Speed, throttle, brake, gear, DRS, tire compound
- 📍 **Position Tracking**: Real-time position updates with lap information
- 🏁 **Interactive Leaderboard**: Click to view detailed driver data
- 🌡️ **Weather Data**: Track temperature, air temperature, humidity, wind
- 🛞 **Tire Management**: Compound tracking with estimated health

### Track Visualization
- 🗺️ **Full Track Layout**: Inner/outer boundaries with proper scaling
- 🟢 **DRS Zones**: Highlighted activation zones
- ⚠️ **Race Events**: DNF markers, flags (yellow/red/safety car), safety car periods
- 🎯 **Auto-scaling**: Dynamic viewport adjustment

### Mobile Support
- 📱 **Responsive Design**: Optimized layout for mobile devices
- 👆 **Touch Controls**: Tap to select drivers, expandable leaderboard
- 📲 **Mobile Telemetry**: Bottom drawer with detailed driver stats
- 🎛️ **Compact Controls**: Space-efficient playback controls

## Tech Stack

- **Backend**: Flask 3.0.3 + Flask-SocketIO 5.4.1
- **Frontend**: HTML5 Canvas + Vanilla JavaScript + Socket.IO
- **Data Source**: FastF1 3.4.11 (Official F1 telemetry API)
- **Deployment**: Railway / Cloudflare Tunnel / Local

## Installation

### Requirements
- Python 3.8+
- pip

### Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/leibowivz/f1-race-replay-web.git
   cd f1-race-replay-web
   ```

2. **Create virtual environment** (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**:
   ```bash
   python app.py
   ```

5. **Access the app**:
   - Open your browser and navigate to `http://localhost:5021`
   - Select a season, race, and session type
   - Click "Load Race" and enjoy!

## Local Deployment with Public Access

### Option 1: Cloudflare Tunnel (Free, Recommended)

1. **Install Cloudflare Tunnel**:
   ```bash
   # macOS
   brew install cloudflared
   
   # Linux
   wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
   sudo dpkg -i cloudflared-linux-amd64.deb
   
   # Windows
   # Download from https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/
   ```

2. **Start Flask app**:
   ```bash
   python app.py
   ```

3. **Create tunnel** (in a separate terminal):
   ```bash
   cloudflared tunnel --url http://localhost:5021
   ```

4. **Access via the provided URL**:
   - Cloudflare will generate a public URL (e.g., `https://example.trycloudflare.com`)
   - Share this URL to access from anywhere
   - No configuration needed!

### Option 2: Railway Deployment

1. **Create Railway account**: https://railway.app

2. **Install Railway CLI**:
   ```bash
   npm install -g @railway/cli
   ```

3. **Login and deploy**:
   ```bash
   railway login
   railway init
   railway up
   ```

4. **Configure**:
   - Railway will auto-detect the Flask app
   - Uses `railway.json` for configuration
   - Supports auto-sleep to save resources

## Usage Guide

### Basic Workflow

1. **Select Season**: Choose from 2018-2025
2. **Choose Race**: Pick a Grand Prix from the calendar
3. **Select Session**: Race (R), Qualifying (Q), or Sprint (S)
4. **Load Data**: Click "Load Race" (first load takes 30-100s)
5. **Watch Replay**: Use playback controls

### Keyboard Shortcuts

- **Space**: Play/Pause
- **← →**: Seek backward/forward
- **1-4**: Change speed (0.5x, 1x, 2x, 4x)
- **R**: Restart from beginning
- **Click driver**: View detailed telemetry

### Mobile Usage

- **Tap driver**: Open telemetry drawer at bottom
- **Tap leaderboard title**: Expand/collapse leaderboard
- **Pinch/zoom**: Not supported (use native browser zoom)

## Configuration

### Environment Variables

```bash
# Server port (default: 5021)
PORT=5021

# Cache directory (default: /tmp/.fastf1-cache)
CACHE_DIR=/path/to/cache

# Railway environment detection
RAILWAY_ENVIRONMENT=production
```

### Cache Management

- FastF1 caches race data in `CACHE_DIR`
- First load: 30-100 seconds (downloads data)
- Subsequent loads: 2-3 seconds (uses cache)
- Cache size: ~2-5MB per race session

## Performance Notes

### Local Deployment
- **Latency**: 10-50ms (optimal)
- **Playback**: Smooth 5+ FPS rendering
- **Memory**: ~170MB idle, 300-500MB active
- **CPU**: <1% idle, 5-15% during playback

### Cloud Deployment (Railway)
- **Latency**: 100-300ms (depends on location)
- **Playback**: May experience buffering
- **Recommendation**: Use local + Cloudflare Tunnel for best performance

## Troubleshooting

### Race Not Loading
- **First time**: Wait 30-100s for data download
- **Check logs**: `tail -f /tmp/f1-app-local.log` (or Railway logs)
- **Clear cache**: Delete `CACHE_DIR` and reload

### WebSocket Connection Failed
- **Check port**: Make sure 5021 is not in use
- **Firewall**: Allow inbound connections on port 5021
- **Browser**: Try disabling extensions or use incognito mode

### Mobile Layout Issues
- **Clear cache**: Hard refresh (Ctrl+Shift+R / Cmd+Shift+R)
- **Browser**: Use Chrome/Safari for best compatibility
- **Screen size**: Optimized for 375px+ width

## Development

### Project Structure

```
f1-race-replay-web/
├── app.py                 # Flask server + Socket.IO handlers
├── src/
│   └── f1_data.py        # FastF1 data processing
├── templates/
│   ├── index.html        # Home page (select race)
│   ├── index_f1.html     # Race selection with F1 branding
│   ├── qualifying.html   # Qualifying results page
│   └── viewer.html       # Race replay viewer (with mobile support)
├── static/
│   ├── viewer.js         # Canvas rendering + WebSocket client
│   ├── viewer-enhanced.css
│   └── f1-theme.css
├── requirements.txt      # Python dependencies
├── railway.json          # Railway configuration
└── README.md
```

### Adding New Features

1. **Backend**: Modify `app.py` or `src/f1_data.py`
2. **Frontend**: Update `templates/viewer.html` or `static/viewer.js`
3. **Test locally**: `python app.py`
4. **Commit**: `git add . && git commit -m "Feature: description"`
5. **Deploy**: `git push` (Railway auto-deploys on push)

## Credits

### Original Project
Based on [f1-race-replay](https://github.com/IAmTomShaw/f1-race-replay) by Tom Shaw  
Converted from desktop (Arcade/PySide6) to web (Flask/Canvas)

### Data Source
Race data provided by [FastF1](https://github.com/theOehrly/Fast-F1)  
Official F1 timing data courtesy of Formula 1

### Built With
- Flask & Flask-SocketIO
- FastF1 API
- HTML5 Canvas
- Socket.IO

## License

MIT License - See [LICENSE](LICENSE) for details

---

**Version**: 2.0.0 (Mobile Enhanced)  
**Last Updated**: February 10, 2026  
**Built with** 🛸 **by OpenRiot**
