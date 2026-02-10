# F1 Race Replay - Web Version 🏎️ 🏁

A web-based Formula 1 race visualization and replay tool built with Flask, Socket.IO, and HTML5 Canvas.

## Features

- 🌐 **Web-Based**: Access from any browser, no desktop app needed
- 🏁 **Live Race Replay**: Watch F1 races with real-time telemetry
- 📊 **Interactive Leaderboard**: See driver positions, speeds, and tire compounds
- ⏯️ **Playback Controls**: Play, pause, seek, and adjust speed (0.5x - 4x)
- 🎨 **Visual Track Display**: HTML5 Canvas visualization with team colors
- 📡 **Real-time Updates**: WebSocket connection for smooth replay

## Tech Stack

- **Backend**: Flask + Flask-SocketIO
- **Frontend**: HTML5 Canvas + JavaScript
- **Data**: FastF1 API for official F1 telemetry
- **Deployment**: Railway (ready to deploy)

## Local Development

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the App**:
   ```bash
   python app.py
   ```

3. **Open Browser**:
   Navigate to `http://localhost:5000`

## Railway Deployment

1. **Create Railway Project**:
   ```bash
   railway init
   ```

2. **Deploy**:
   ```bash
   railway up
   ```

The app is configured with `railway.json` and `Procfile` for automatic deployment.

## Usage

1. Select a season (2018-2025)
2. Choose a race weekend
3. Pick session type (Race/Qualifying/Sprint)
4. Click "Load Race"
5. Use controls to play, pause, and navigate the replay

## Data Source

Race data is provided by [FastF1](https://github.com/theOehrly/Fast-F1), which accesses official F1 timing data.

## Original Project

Based on [f1-race-replay](https://github.com/IAmTomShaw/f1-race-replay) by Tom Shaw.
Converted from desktop (Arcade/PySide6) to web (Flask/Canvas) for cloud deployment.

## License

MIT License - See original project for details.

---

Built with 🛸 by OpenRiot for Nan Shang
# F1 Race Replay Web - Updated Mon Feb  9 19:33:38 CST 2026
