// F1 Race Replay Viewer - JavaScript
const canvas = document.getElementById('track');
const ctx = canvas.getContext('2d');
const socket = io();

// State
let isPlaying = false;
let currentSpeed = 1.0;
let totalFrames = 0;
let currentFrame = 0;
let drivers = [];
let trackBounds = { minX: 0, maxX: 0, minY: 0, maxY: 0 };
let selectedDriver = null;
let eventName = '';
let currentLap = 1;
let totalLaps = 0;
let weatherData = null;
let trackData = null;
let drsZones = [];
let raceEvents = [];

// Frame rate control (5 FPS target)
let lastRenderTime = 0;
const FRAME_INTERVAL = 200; // ms between renders (5 FPS)
let pendingFrameData = null;

// Resize canvas to match display size
function resizeCanvas() {
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    
    // Force explicit dimensions
    const width = Math.floor(rect.width);
    const height = Math.floor(rect.height);
    
    if (width === 0 || height === 0) {
        console.warn('Canvas has zero size, using fallback');
        canvas.width = window.innerWidth - 340 - 260;
        canvas.height = window.innerHeight - 60 - 80;
    } else {
        canvas.width = width;
        canvas.height = height;
    }
    
    console.log(`✅ Canvas resized: ${canvas.width}x${canvas.height} (CSS: ${width}x${height})`);
    
    drawFrame();
}

window.addEventListener('resize', resizeCanvas);
resizeCanvas();

// Check if this is qualifying replay mode
const urlParams = new URLSearchParams(window.location.search);
const isQualifyingMode = urlParams.get('mode') === 'qualifying';

if (isQualifyingMode) {
    // Load qualifying lap data
    const qualiData = localStorage.getItem('quali_replay');
    if (qualiData) {
        const data = JSON.parse(qualiData);
        console.log('Loading qualifying lap:', data);
        
        fetch('/api/load_qualifying_lap', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        }).then(r => r.json()).then(result => {
            console.log('✅ Qualifying lap loaded:', result);
        });
    }
}

// Socket events
socket.on('connect', () => {
    console.log('✅ Connected to server');
    socket.emit('seek', { frame: 0 });
});

socket.on('frame_update', (data) => {
    // Store frame data
    pendingFrameData = data;
    
    // Throttle rendering to target FPS
    const now = Date.now();
    const timeSinceLastRender = now - lastRenderTime;
    const targetInterval = FRAME_INTERVAL / currentSpeed;
    
    if (timeSinceLastRender >= targetInterval || currentFrame === 0) {
        renderFrame(data);
        lastRenderTime = now;
    }
});

function renderFrame(data) {
    if (currentFrame % 100 === 0 || currentFrame === 0) {
        console.log('📊 Frame:', data.frame, '/', data.total_frames);
    }
    currentFrame = data.frame;
    totalFrames = data.total_frames;
    drivers = data.drivers;
    
    if (data.weather) {
        weatherData = data.weather;
        updateWeather();
    }
    
    // Update track bounds dynamically
    if (drivers.length > 0 && !trackData) {
        const xs = drivers.map(d => d.x).filter(x => x !== 0 && !isNaN(x));
        const ys = drivers.map(d => d.y).filter(y => y !== 0 && !isNaN(y));
        
        if (xs.length > 0 && ys.length > 0) {
            const newBounds = {
                minX: Math.min(...xs) - 500,
                maxX: Math.max(...xs) + 500,
                minY: Math.min(...ys) - 500,
                maxY: Math.max(...ys) + 500
            };
            
            if (trackBounds.minX === 0 && trackBounds.maxX === 0) {
                trackBounds = newBounds;
            }
        }
    }
    
    drawFrame();
    updateLeaderboard();
    if (selectedDriver) {
        updateDriverTelemetry();
    }
    updateProgress();
}

socket.on('replay_ended', () => {
    isPlaying = false;
    document.getElementById('playBtn').innerHTML = '▶ Play';
});

socket.on('initial_load_complete', (data) => {
    console.log('Race loaded:', data.total_frames, 'frames');
    totalFrames = data.total_frames;
    
    if (data.event_name) {
        eventName = data.event_name;
        document.getElementById('eventName').textContent = eventName;
        
        // Add detailed session info
        let details = [];
        if (data.circuit_name) details.push(data.circuit_name);
        if (data.country && data.country !== data.circuit_name) details.push(data.country);
        if (data.year) details.push(`${data.year}`);
        if (data.round) details.push(`Round ${data.round}`);
        
        if (details.length > 0) {
            document.getElementById('eventDetails').textContent = details.join(' • ');
        }
    }
    if (data.total_laps) {
        totalLaps = data.total_laps;
    }
    
    // Load race events
    if (data.race_events) {
        raceEvents = data.race_events;
        console.log('✅ Race events:', raceEvents.length);
        drawEventMarkers();
    }
    
    if (data.track_data) {
        trackData = data.track_data;
        console.log('✅ Track data:', trackData.x.length, 'points');
        
        // Calculate tight bounds from actual track data
        const xs = trackData.x.filter(x => !isNaN(x) && x !== 0);
        const ys = trackData.y.filter(y => !isNaN(y) && y !== 0);
        
        if (xs.length > 0 && ys.length > 0) {
            const minX = Math.min(...xs);
            const maxX = Math.max(...xs);
            const minY = Math.min(...ys);
            const maxY = Math.max(...ys);
            
            // Add minimal 5% padding
            const padX = (maxX - minX) * 0.05;
            const padY = (maxY - minY) * 0.05;
            
            trackBounds = {
                minX: minX - padX,
                maxX: maxX + padX,
                minY: minY - padY,
                maxY: maxY + padY
            };
            
            console.log('✅ Track bounds:', 
                `X: ${minX.toFixed(0)} to ${maxX.toFixed(0)} (${(maxX-minX).toFixed(0)})`,
                `Y: ${minY.toFixed(0)} to ${maxY.toFixed(0)} (${(maxY-minY).toFixed(0)})`);
        }
        
        extractDRSZones();
    }
    
    socket.emit('seek', { frame: 0 });
});

function extractDRSZones() {
    if (!trackData || !trackData.drs) return;
    
    drsZones = [];
    let drsStart = null;
    
    for (let i = 0; i < trackData.drs.length; i++) {
        const drs = trackData.drs[i];
        if (drs === 10 || drs === 12 || drs === 14) {
            if (drsStart === null) drsStart = i;
        } else {
            if (drsStart !== null) {
                drsZones.push({ start: drsStart, end: i - 1 });
                drsStart = null;
            }
        }
    }
    
    if (drsStart !== null) {
        drsZones.push({ start: drsStart, end: trackData.drs.length - 1 });
    }
    
    console.log('✅ DRS zones:', drsZones.length);
}

// Drawing
function drawFrame() {
    ctx.fillStyle = '#1a1a1a';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    if (drivers.length === 0 && (!trackData || trackData.x.length === 0)) return;
    
    // Calculate scale to fill canvas
    const padding = 40;
    const availableWidth = canvas.width - padding * 2;
    const availableHeight = canvas.height - padding * 2;
    
    const trackWidth = trackBounds.maxX - trackBounds.minX;
    const trackHeight = trackBounds.maxY - trackBounds.minY;
    
    if (trackWidth <= 0 || trackHeight <= 0) {
        console.warn('Invalid track bounds');
        return;
    }
    
    const scaleX = availableWidth / trackWidth;
    const scaleY = availableHeight / trackHeight;
    const scale = Math.min(scaleX, scaleY);
    
    console.log(`📐 Canvas: ${canvas.width}x${canvas.height}, Track: ${trackWidth.toFixed(0)}x${trackHeight.toFixed(0)}, Scale: ${scale.toFixed(4)}`);
    
    // Center the track
    const scaledWidth = trackWidth * scale;
    const scaledHeight = trackHeight * scale;
    const offsetX = (canvas.width - scaledWidth) / 2;
    const offsetY = (canvas.height - scaledHeight) / 2;
    
    function transformX(x) {
        return (x - trackBounds.minX) * scale + offsetX;
    }
    
    function transformY(y) {
        return (y - trackBounds.minY) * scale + offsetY;
    }
    
    // Draw track
    if (trackData && trackData.x.length > 0) {
        // Draw track boundaries (inner/outer)
        if (trackData.x_inner && trackData.x_outer) {
            // Outer boundary
            ctx.strokeStyle = '#666';
            ctx.lineWidth = 3;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            ctx.globalAlpha = 0.6;
            ctx.beginPath();
            for (let i = 0; i < trackData.x_outer.length; i++) {
                const x = transformX(trackData.x_outer[i]);
                const y = transformY(trackData.y_outer[i]);
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.stroke();
            
            // Inner boundary
            ctx.beginPath();
            for (let i = 0; i < trackData.x_inner.length; i++) {
                const x = transformX(trackData.x_inner[i]);
                const y = transformY(trackData.y_inner[i]);
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.stroke();
            ctx.globalAlpha = 1.0;
        } else {
            // Fallback: center line only
            ctx.strokeStyle = '#555';
            ctx.lineWidth = 30;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            ctx.globalAlpha = 0.4;
            ctx.beginPath();
            
            for (let i = 0; i < trackData.x.length; i++) {
                const x = transformX(trackData.x[i]);
                const y = transformY(trackData.y[i]);
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.stroke();
            ctx.globalAlpha = 1.0;
        }
        
        // DRS zones
        drsZones.forEach(zone => {
            ctx.strokeStyle = '#00ff00';
            ctx.lineWidth = 35;
            ctx.globalAlpha = 0.3;
            ctx.beginPath();
            
            for (let i = zone.start; i <= zone.end && i < trackData.x.length; i++) {
                const x = transformX(trackData.x[i]);
                const y = transformY(trackData.y[i]);
                if (i === zone.start) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.stroke();
            ctx.globalAlpha = 1.0;
        });
        
        // Finish line
        if (trackData.x.length > 1) {
            const x0 = transformX(trackData.x[0]);
            const y0 = transformY(trackData.y[0]);
            const x1 = transformX(trackData.x[1]);
            const y1 = transformY(trackData.y[1]);
            
            const dx = x1 - x0;
            const dy = y1 - y0;
            const len = Math.sqrt(dx*dx + dy*dy);
            const nx = -dy / len * 30;
            const ny = dx / len * 30;
            
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 4;
            ctx.setLineDash([10, 10]);
            ctx.beginPath();
            ctx.moveTo(x0 - nx, y0 - ny);
            ctx.lineTo(x0 + nx, y0 + ny);
            ctx.stroke();
            ctx.setLineDash([]);
        }
    }
    
    // Draw drivers
    drivers.forEach(driver => {
        const x = transformX(driver.x);
        const y = transformY(driver.y);
        const isSelected = selectedDriver === driver.code;
        
        // Highlight ring for selected driver
        if (isSelected) {
            ctx.strokeStyle = '#ffff00';
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.arc(x, y, 14, 0, Math.PI * 2);
            ctx.stroke();
        }
        
        // Driver dot
        ctx.fillStyle = driver.is_out ? '#666' : driver.color;
        ctx.beginPath();
        ctx.arc(x, y, isSelected ? 10 : 8, 0, Math.PI * 2);
        ctx.fill();
        
        // Driver label (always show, not just for selected)
        ctx.fillStyle = '#000';
        ctx.font = 'bold 10px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        
        // Background for readability
        const textWidth = ctx.measureText(driver.code).width;
        ctx.fillStyle = driver.is_out ? '#666' : driver.color;
        ctx.fillRect(x - textWidth/2 - 2, y - 16, textWidth + 4, 12);
        
        // Text
        ctx.fillStyle = '#fff';
        ctx.fillText(driver.code, x, y - 10);
    });
}

// Leaderboard
function updateLeaderboard() {
    const content = document.getElementById('leaderboard');
    const sorted = [...drivers].sort((a, b) => a.position - b.position);
    
    if (sorted.length > 0) {
        currentLap = sorted[0].lap;
        document.getElementById('lapInfo').textContent = `Lap ${currentLap} / ${totalLaps || '?'}`;
    }
    
    content.innerHTML = sorted.map(driver => `
        <div class="driver-row ${driver.is_out ? 'out' : ''} ${selectedDriver === driver.code ? 'selected' : ''}" 
             style="border-left-color: ${driver.color}"
             onclick="selectDriver('${driver.code}')">
            <div class="driver-pos">${driver.position}</div>
            <div class="driver-code">${driver.code}</div>
            <div class="driver-stats">
                L${driver.lap} | ${Math.round(driver.speed)} km/h
                ${driver.is_out ? ' | OUT' : ''}
            </div>
        </div>
    `).join('');
}

function selectDriver(code) {
    if (selectedDriver === code) {
        selectedDriver = null;
        document.getElementById('driverInfoPanel').style.display = 'none';
    } else {
        selectedDriver = code;
        document.getElementById('driverInfoPanel').style.display = 'block';
    }
    // Use pending frame data if available, otherwise use current state
    if (pendingFrameData) {
        renderFrame(pendingFrameData);
    } else {
        updateDriverTelemetry();
        drawFrame();
    }
}

function updateDriverTelemetry() {
    if (!selectedDriver) return;
    
    const driver = drivers.find(d => d.code === selectedDriver);
    if (!driver) return;
    
    // Format percentage bars
    const throttleBar = createBar(driver.throttle || 0, '#00ff00');
    const brakeBar = createBar(driver.brake || 0, '#ff0000');
    
    // DRS status
    const drsStatus = driver.drs === 10 || driver.drs === 12 || driver.drs === 14 ? 
        '🟢 ACTIVE' : (driver.drs === 8 ? '🟡 AVAILABLE' : '⚪ OFF');
    
    // Tyre compound
    const tyreNames = ['', 'SOFT', 'MEDIUM', 'HARD', 'INTERMEDIATE', 'WET'];
    const tyreName = tyreNames[driver.tyre] || 'UNKNOWN';
    const tyreColors = ['', '#ff0000', '#ffff00', '#ffffff', '#00ff00', '#0000ff'];
    const tyreColor = tyreColors[driver.tyre] || '#888';
    
    const content = document.getElementById('driverTelemetry');
    content.innerHTML = `
        <div style="display: flex; align-items: center; margin-bottom: 12px;">
            <div style="width: 24px; height: 24px; background: ${driver.color}; border-radius: 50%; margin-right: 10px;"></div>
            <strong style="font-size: 18px;">${driver.code}</strong>
        </div>
        
        <div class="telemetry-row">
            <span>Speed</span>
            <strong>${Math.round(driver.speed)} km/h</strong>
        </div>
        <div class="telemetry-row">
            <span>Gear</span>
            <strong>${driver.gear || 'N'}</strong>
        </div>
        <div class="telemetry-row">
            <span>Throttle</span>
            <div style="flex: 1;">${throttleBar}</div>
            <strong style="margin-left: 8px;">${Math.round(driver.throttle || 0)}%</strong>
        </div>
        <div class="telemetry-row">
            <span>Brake</span>
            <div style="flex: 1;">${brakeBar}</div>
            <strong style="margin-left: 8px;">${Math.round(driver.brake || 0)}%</strong>
        </div>
        <div class="telemetry-row">
            <span>DRS</span>
            <strong>${drsStatus}</strong>
        </div>
        <div class="telemetry-row">
            <span>Tyre</span>
            <strong style="color: ${tyreColor}">${tyreName}</strong>
        </div>
        <div class="telemetry-row">
            <span>Tyre Age</span>
            <strong>${Math.round(driver.tyre_life || 0)} laps</strong>
        </div>
        <div class="telemetry-row">
            <span>Tyre Health</span>
            <div style="flex: 1;">${createTyreHealthBar(driver.tyre_life, tyreName)}</div>
        </div>
        <div class="telemetry-row">
            <span>Position</span>
            <strong>P${driver.position}</strong>
        </div>
        <div class="telemetry-row">
            <span>Lap</span>
            <strong>${driver.lap}</strong>
        </div>
        <div class="telemetry-row">
            <span>Status</span>
            <strong>${driver.is_out ? '❌ OUT' : '✅ Racing'}</strong>
        </div>
    `;
}

function createBar(percentage, color) {
    const pct = Math.min(100, Math.max(0, percentage));
    return `
        <div style="background: #333; height: 8px; border-radius: 4px; overflow: hidden; flex: 1;">
            <div style="background: ${color}; height: 100%; width: ${pct}%; transition: width 0.1s;"></div>
        </div>
    `;
}

function createTyreHealthBar(tyreLife, tyreType) {
    // Estimate tyre health based on compound and age
    // SOFT: 15 laps max, MEDIUM: 25 laps, HARD: 35 laps
    const maxLaps = {
        'SOFT': 15,
        'MEDIUM': 25,
        'HARD': 35,
        'INTERMEDIATE': 20,
        'WET': 20
    };
    
    const maxLife = maxLaps[tyreType] || 25;
    const health = Math.max(0, Math.min(100, ((maxLife - tyreLife) / maxLife) * 100));
    
    let color = '#00ff00'; // Green
    if (health < 30) color = '#ff0000'; // Red
    else if (health < 60) color = '#ffaa00'; // Orange
    
    return `
        <div style="background: #333; height: 8px; border-radius: 4px; overflow: hidden; flex: 1;">
            <div style="background: ${color}; height: 100%; width: ${health}%; transition: width 0.3s;"></div>
        </div>
    `;
}

function drawEventMarkers() {
    const container = document.getElementById('progressContainer');
    // Clear existing markers
    container.querySelectorAll('.event-marker').forEach(el => el.remove());
    
    if (!raceEvents || totalFrames === 0) return;
    
    raceEvents.forEach(event => {
        const percent = (event.frame / totalFrames) * 100;
        const marker = document.createElement('div');
        marker.className = `event-marker ${event.type}`;
        marker.style.left = `${percent}%`;
        marker.title = event.label || event.type.toUpperCase();
        container.appendChild(marker);
    });
}

// Weather
function updateWeather() {
    if (!weatherData) return;
    
    document.getElementById('weatherPanel').style.display = 'block';
    document.getElementById('weatherTrack').textContent = 
        weatherData.track_temp ? `${Math.round(weatherData.track_temp)}°C` : '--°C';
    document.getElementById('weatherAir').textContent = 
        weatherData.air_temp ? `${Math.round(weatherData.air_temp)}°C` : '--°C';
    document.getElementById('weatherHumidity').textContent = 
        weatherData.humidity ? `${Math.round(weatherData.humidity)}%` : '--%';
    document.getElementById('weatherWind').textContent = 
        weatherData.wind_speed ? `${Math.round(weatherData.wind_speed)} km/h` : '--';
}

// Progress
function updateProgress() {
    const percent = totalFrames > 0 ? (currentFrame / totalFrames) * 100 : 0;
    document.getElementById('progressBar').style.width = percent + '%';
    
    const currentTime = Math.floor(currentFrame / 25);
    const totalTime = Math.floor(totalFrames / 25);
    document.getElementById('timeDisplay').textContent = 
        `${formatTime(currentTime)} / ${formatTime(totalTime)}`;
}

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Controls
function togglePlay() {
    isPlaying = !isPlaying;
    const btn = document.getElementById('playBtn');
    
    if (isPlaying) {
        btn.innerHTML = '⏸ Pause';
        socket.emit('play');
    } else {
        btn.innerHTML = '▶ Play';
        socket.emit('pause');
    }
}

function restart() {
    socket.emit('seek', { frame: 0 });
    if (!isPlaying) togglePlay();
}

function changeSpeed(speed) {
    currentSpeed = speed;
    socket.emit('set_speed', { speed });
    
    document.querySelectorAll('.speed-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');
}

function seek(event) {
    const rect = event.target.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const percent = x / rect.width;
    const frame = Math.floor(percent * totalFrames);
    socket.emit('seek', { frame });
}

// Keyboard controls
document.addEventListener('keydown', (e) => {
    if (e.key === ' ' || e.key === 'Spacebar') {
        e.preventDefault();
        togglePlay();
    } else if (e.key === 'r' || e.key === 'R') {
        restart();
    } else if (e.key === '1') {
        changeSpeed(0.5);
    } else if (e.key === '2') {
        changeSpeed(1.0);
    } else if (e.key === '3') {
        changeSpeed(2.0);
    } else if (e.key === '4') {
        changeSpeed(4.0);
    } else if (e.key === 'ArrowLeft') {
        socket.emit('seek', { frame: Math.max(0, currentFrame - 25) });
    } else if (e.key === 'ArrowRight') {
        socket.emit('seek', { frame: Math.min(totalFrames - 1, currentFrame + 25) });
    }
});
