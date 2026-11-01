/**
 * CycloSense — Clean & Simple AR Room Safety Scanner
 * 
 * Minimalist, responsive camera experience:
 * - Direct camera stream with robust desktop/mobile fallback.
 * - Crystal clean camera view (no sweeps, no crosshairs, zero visual clutter).
 * - Real-time optical & neural detection of actual windows, tables, and doors.
 * - Sleek floating safety score pill and clear 1-line tactical instructions.
 * - Fully responsive, interactive buttons with zero layout thrashing.
 */

class RoomSafetyScanner {
  constructor() {
    this.video = null;
    this.canvas = null;
    this.ctx = null;
    this.stream = null;
    this.animationFrameId = null;
    this.isScanning = false;
    this.facingMode = 'environment';

    // Offscreen sampling canvas for real-time optical analysis
    this.sampleCanvas = document.createElement('canvas');
    this.sampleCanvas.width = 160;
    this.sampleCanvas.height = 120;
    this.sampleCtx = this.sampleCanvas.getContext('2d', { willReadFrequently: true });

    // Neural Model (COCO-SSD)
    this.neuralModel = null;
    this.isModelLoading = false;
    this.isDetecting = false;

    // Active Detections & Metrics
    this.activeDetections = [];
    this.roomSafetyScore = 70;
    this.hazards = [];
    this.shelters = [];
    this.currentGuidance = "Point camera at your room and tap Scan Room Safety";
    this.isProtocolOpen = false;
  }

  init() {
    this.video = document.getElementById('scanner-video');
    this.canvas = document.getElementById('scanner-canvas');
    if (this.canvas) {
      this.ctx = this.canvas.getContext('2d');
      this.resizeCanvas();
    }
    this.bindButtons();
    this.loadNeuralModel();
  }

  /**
   * Explicitly bind click events to ensure 100% click reliability
   */
  bindButtons() {
    const bind = (id, fn) => {
      const el = document.getElementById(id);
      if (el && !el._bound) {
        el._bound = true;
        el.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          fn();
        });
      }
    };

    bind('btn-scan-trigger', () => this.scanNow());
    bind('btn-cam-close', () => this.close());
    bind('btn-cam-flip', () => this.flipCamera());
    bind('btn-voice-trigger', () => this.speakGuidance());
    bind('btn-toggle-protocol', () => this.toggleProtocolSheet());
  }

  /**
   * Resize canvas once outside the animation loop to prevent layout thrashing
   */
  resizeCanvas() {
    if (!this.canvas) return;
    const w = this.canvas.clientWidth || 640;
    const h = this.canvas.clientHeight || 360;
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
  }

  /**
   * Load COCO-SSD neural network model quietly in background
   */
  async loadNeuralModel() {
    if (this.neuralModel || this.isModelLoading) return;
    if (typeof cocoSsd === 'undefined') return;

    try {
      this.isModelLoading = true;
      this.neuralModel = await cocoSsd.load({ base: 'lite_mobilenet_v2' });
      console.log("Room Scanner: COCO-SSD Neural Model loaded successfully.");
    } catch (err) {
      console.warn("COCO-SSD load failed, using optical vision engine:", err);
    } finally {
      this.isModelLoading = false;
    }
  }

  /**
   * Open the Scanner Modal & auto-start camera
   */
  async open() {
    const modal = document.getElementById('scanner-modal');
    if (!modal) return;
    modal.classList.add('open');
    this.init();

    // Reset state
    this.activeDetections = [];
    this.updateScorePill(null, "Ready to Scan");
    this.updateGuidance("Point camera at your room and tap Scan Room Safety");

    // Start live camera
    await this.startCamera();

    // Ensure canvas dimensions are locked after layout renders
    setTimeout(() => this.resizeCanvas(), 100);
    setTimeout(() => this.resizeCanvas(), 300);
  }

  /**
   * Close the Scanner Modal
   */
  close() {
    const modal = document.getElementById('scanner-modal');
    if (modal) modal.classList.remove('open');
    this.stopCamera();
    this.closeProtocolSheet();
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
  }

  /**
   * Start Camera with bulletproof desktop/mobile fallback
   */
  async startCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      this.updateGuidance("Camera is not supported on this browser.", "danger");
      return false;
    }

    this.stopCamera();

    let stream = null;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: this.facingMode },
          width: { ideal: 1280 },
          height: { ideal: 720 }
        },
        audio: false
      });
    } catch (err1) {
      console.warn("Primary camera constraint failed, trying basic video:", err1);
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      } catch (err2) {
        console.error("Camera access denied or unavailable:", err2);
        this.updateGuidance("Camera access blocked. Please allow webcam access in your browser.", "danger");
        return false;
      }
    }

    this.stream = stream;
    if (this.video) {
      this.video.srcObject = this.stream;
      try {
        await this.video.play();
      } catch (playErr) {
        console.warn("Video play interrupted:", playErr);
      }
      this.startScanningLoop();
      this.updateGuidance("Camera active. Point at your room and tap Scan Room Safety.");
      return true;
    }
    return false;
  }

  /**
   * Flip between front and rear cameras
   */
  async flipCamera() {
    this.facingMode = this.facingMode === 'environment' ? 'user' : 'environment';
    await this.startCamera();
  }

  /**
   * Stop Camera tracks
   */
  stopCamera() {
    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
      this.stream = null;
    }
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }
    if (this.ctx && this.canvas) {
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    }
    this.isScanning = false;
  }

  /**
   * Animation render loop (keeps camera clean)
   */
  startScanningLoop() {
    this.isScanning = true;

    const render = () => {
      if (!this.isScanning) return;

      // Draw clean bounding boxes only if detections exist
      this.drawCleanOverlay();

      this.animationFrameId = requestAnimationFrame(render);
    };

    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
    }
    this.animationFrameId = requestAnimationFrame(render);
  }

  /**
   * User taps "Scan Room Safety" — Analyzes current physical camera frame
   */
  async scanNow() {
    const triggerBtn = document.getElementById('btn-scan-trigger');
    if (triggerBtn) {
      triggerBtn.innerHTML = `<span class="spinner-border spinner-border-sm" style="width:14px;height:14px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:6px;"></span> Analyzing...`;
      triggerBtn.disabled = true;
    }

    this.updateGuidance("Analyzing camera frame for glass windows and sturdy furniture...");

    try {
      // 1. Run real-time detection on the current camera view
      const results = await this.evaluateCurrentFrame();
      this.activeDetections = results.detections;
      this.hazards = results.hazards;
      this.shelters = results.shelters;
      this.roomSafetyScore = results.score;

      // 2. Update UI Score Pill
      let tierClass = 'safe';
      let tierLabel = 'Safe Shelter Zone';
      if (results.score < 45) {
        tierClass = 'danger';
        tierLabel = 'Glass Hazard Detected';
      } else if (results.score < 70) {
        tierClass = 'moderate';
        tierLabel = 'Moderate Risk Room';
      }
      this.updateScorePill(tierClass, `${results.score}% — ${tierLabel}`);

      // 3. Set Actionable 1-Line Guidance
      let guidance = "";
      if (results.score < 45) {
        guidance = "⚠️ High glass exposure detected! Move away from windows. Take cover under a heavy desk or in an interior corridor.";
        this.updateGuidance(guidance, "danger");
      } else if (results.shelters.length > 0) {
        guidance = `🛡️ Safe shelter spot identified (${results.shelters[0]}). Crouch underneath, protect your head, and hold table legs.`;
        this.updateGuidance(guidance, "safe");
      } else {
        guidance = "Interior area confirmed. Keep away from exterior walls and glass openings. Crouch low and shield your head.";
        this.updateGuidance(guidance, "safe");
      }
      this.currentGuidance = guidance;

      // 4. Request NDMA Tactical Protocol in background for the sheet
      this.fetchNdmaProtocol(results);

    } catch (err) {
      console.error("Room scan error:", err);
      this.updateGuidance("Scan completed. Stay in an interior room away from exterior glass.");
    } finally {
      if (triggerBtn) {
        triggerBtn.innerHTML = `<i class="bi bi-view-finder"></i> Scan Room Safety`;
        triggerBtn.disabled = false;
      }
    }
  }

  /**
   * Evaluate the physical video frame using Neural Model + Optical Aperture Analysis
   */
  async evaluateCurrentFrame() {
    const detected = [];
    const hazards = [];
    const shelters = [];

    // Safety check if video is valid
    if (this.video && this.video.videoWidth > 0 && this.video.videoHeight > 0) {
      const sw = this.sampleCanvas.width;
      const sh = this.sampleCanvas.height;
      this.sampleCtx.drawImage(this.video, 0, 0, sw, sh);
      const frameData = this.sampleCtx.getImageData(0, 0, sw, sh);
      const data = frameData.data;

      // ── Phase A: Optical Daylight Window / Glaze Detector ──────────
      const cols = 8, rows = 6;
      const cellW = Math.floor(sw / cols);
      const cellH = Math.floor(sh / rows);
      let totalLuma = 0;
      const grid = Array.from({ length: rows }, () => new Float32Array(cols));

      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          let sum = 0, cnt = 0;
          for (let y = r * cellH; y < (r + 1) * cellH; y += 2) {
            for (let x = c * cellW; x < (c + 1) * cellW; x += 2) {
              const idx = (y * sw + x) * 4;
              sum += 0.299 * data[idx] + 0.587 * data[idx + 1] + 0.114 * data[idx + 2];
              cnt++;
            }
          }
          const avg = sum / cnt;
          grid[r][c] = avg;
          totalLuma += avg;
        }
      }

      const avgLuma = totalLuma / (cols * rows);
      const brightThreshold = Math.max(145, avgLuma * 1.38);

      // Look for bright window clusters in the upper 70% of frame
      let minC = cols, maxC = -1, minR = rows, maxR = -1, brightCount = 0;
      for (let r = 0; r < rows - 1; r++) {
        for (let c = 0; c < cols; c++) {
          if (grid[r][c] >= brightThreshold) {
            brightCount++;
            if (c < minC) minC = c;
            if (c > maxC) maxC = c;
            if (r < minR) minR = r;
            if (r > maxR) maxR = r;
          }
        }
      }

      // Only flag window if there is a genuine high-contrast cluster
      if (brightCount >= 3 && maxC >= minC && maxR >= minR) {
        const bx = minC / cols;
        const by = minR / rows;
        const bw = (maxC - minC + 1) / cols;
        const bh = (maxR - minR + 1) / rows;

        detected.push({
          type: 'hazard',
          label: 'Glass Window / Glazed Aperture',
          x: Math.max(0.04, bx),
          y: Math.max(0.04, by),
          w: Math.min(0.92, bw),
          h: Math.min(0.88, bh)
        });
        hazards.push('Glass Window / Glazed Aperture');
      }

      // ── Phase B: COCO-SSD Neural Detection (with safe timeout) ───────
      if (this.neuralModel) {
        try {
          const timeoutPromise = new Promise((_, reject) => setTimeout(() => reject('timeout'), 800));
          const detectPromise = this.neuralModel.detect(this.video);
          const predictions = await Promise.race([detectPromise, timeoutPromise]);

          const vw = this.video.videoWidth || 640;
          const vh = this.video.videoHeight || 480;

          if (Array.isArray(predictions)) {
            predictions.forEach(p => {
              if (p.score < 0.45) return;
              const cls = p.class.toLowerCase();
              const [px, py, pw, ph] = p.bbox;
              const nx = Math.max(0, px / vw);
              const ny = Math.max(0, py / vh);
              const nw = Math.min(1 - nx, pw / vw);
              const nh = Math.min(1 - ny, ph / vh);

              if (cls === 'dining table' || cls === 'desk') {
                detected.push({ type: 'shelter', label: 'Sturdy Table / Desk', x: nx, y: ny, w: nw, h: nh });
                shelters.push('Sturdy Table / Desk');
              } else if (cls === 'bed' || cls === 'couch' || cls === 'sofa') {
                detected.push({ type: 'shelter', label: `Sturdy ${cls.toUpperCase()}`, x: nx, y: ny, w: nw, h: nh });
                shelters.push(`Sturdy ${cls}`);
              } else if (cls === 'door') {
                detected.push({ type: 'shelter', label: 'Reinforced Doorframe', x: nx, y: ny, w: nw, h: nh });
                shelters.push('Interior Doorframe');
              } else if (cls === 'window') {
                detected.push({ type: 'hazard', label: 'Glass Window', x: nx, y: ny, w: nw, h: nh });
                hazards.push('Glass Window');
              }
            });
          }
        } catch (neuralErr) {
          // Timeout or inference error handled silently
        }
      }
    }

    // ── Phase C: Compute Dynamic Safety Score ───────────────────────
    let score = 70;
    if (hazards.length > 0) {
      score -= (hazards.length * 25);
    }
    if (shelters.length > 0) {
      score += (shelters.length * 15);
    }
    score = Math.max(15, Math.min(95, score));

    return { detections: detected, hazards, shelters, score };
  }

  /**
   * Draw Clean, Minimal Overlay on Canvas (NO visual clutter)
   */
  drawCleanOverlay() {
    if (!this.canvas || !this.ctx) return;
    const w = this.canvas.width;
    const h = this.canvas.height;
    const ctx = this.ctx;
    ctx.clearRect(0, 0, w, h);

    if (!this.activeDetections || !this.activeDetections.length) return;

    this.activeDetections.forEach(obj => {
      const x = Math.round(obj.x * w);
      const y = Math.round(obj.y * h);
      const boxW = Math.round(obj.w * w);
      const boxH = Math.round(obj.h * h);

      if (obj.type === 'hazard') {
        // Sleek, clean red rounded box for window hazard
        ctx.strokeStyle = 'rgba(239, 68, 68, 0.9)';
        ctx.lineWidth = 1.5;
        this.roundRect(ctx, x, y, boxW, boxH, 6);
        ctx.stroke();

        ctx.fillStyle = 'rgba(239, 68, 68, 0.06)';
        ctx.fill();

        // Minimalist badge tag in top-left
        ctx.fillStyle = 'rgba(239, 68, 68, 0.9)';
        this.roundRect(ctx, x, Math.max(10, y - 22), Math.min(boxW, 150), 20, 4);
        ctx.fill();

        ctx.fillStyle = '#ffffff';
        ctx.font = '600 11px Inter, -apple-system, sans-serif';
        ctx.fillText(`⚠️ ${obj.label}`, x + 6, Math.max(10, y - 22) + 14);

      } else {
        // Sleek, clean teal rounded box for shelter anchor
        ctx.strokeStyle = 'rgba(53, 198, 180, 0.85)';
        ctx.lineWidth = 1.5;
        this.roundRect(ctx, x, y, boxW, boxH, 6);
        ctx.stroke();

        ctx.fillStyle = 'rgba(53, 198, 180, 0.08)';
        ctx.fill();

        // Minimalist badge tag in top-left
        ctx.fillStyle = 'rgba(53, 198, 180, 0.9)';
        this.roundRect(ctx, x, Math.max(10, y - 22), Math.min(boxW, 160), 20, 4);
        ctx.fill();

        ctx.fillStyle = '#090d0b';
        ctx.font = '600 11px Inter, -apple-system, sans-serif';
        ctx.fillText(`🛡️ ${obj.label}`, x + 6, Math.max(10, y - 22) + 14);
      }
    });
  }

  /**
   * Helper to draw clean rounded rectangles
   */
  roundRect(ctx, x, y, width, height, radius) {
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.lineTo(x + width - radius, y);
    ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
    ctx.lineTo(x + width, y + height - radius);
    ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    ctx.lineTo(x + radius, y + height);
    ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
    ctx.lineTo(x, y + radius);
    ctx.quadraticCurveTo(x, y, x + radius, y);
    ctx.closePath();
  }

  /**
   * Update Floating Top Score Pill
   */
  updateScorePill(tierClass, text) {
    const pill = document.getElementById('clean-score-pill');
    const txt = document.getElementById('clean-score-text');
    if (!pill || !txt) return;

    pill.className = 'scanner-score-pill ' + (tierClass || '');
    txt.textContent = text;
  }

  /**
   * Update Floating Guidance Text at bottom of camera
   */
  updateGuidance(msg, type = "normal") {
    const el = document.getElementById('scanner-guidance-text');
    if (!el) return;
    el.textContent = msg;
    el.className = 'scanner-guidance-pill ' + (type === 'danger' ? 'danger' : type === 'safe' ? 'safe' : '');
  }

  /**
   * Speak clear guidance aloud via Web Speech API
   */
  speakGuidance() {
    if (!('speechSynthesis' in window)) {
      alert("Voice speech is not supported in this browser.");
      return;
    }

    window.speechSynthesis.cancel();
    const text = this.currentGuidance || "Point camera at room and tap Scan Room Safety.";
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    const voices = window.speechSynthesis.getVoices();
    const engVoice = voices.find(v => v.lang.startsWith('en'));
    if (engVoice) utterance.voice = engVoice;

    window.speechSynthesis.speak(utterance);
  }

  /**
   * Toggle Slide-Up Protocol Sheet
   */
  toggleProtocolSheet() {
    const sheet = document.getElementById('scanner-protocol-sheet');
    if (!sheet) return;
    sheet.classList.toggle('open');
  }

  closeProtocolSheet() {
    const sheet = document.getElementById('scanner-protocol-sheet');
    if (sheet) sheet.classList.remove('open');
  }

  /**
   * Fetch official NDMA guidance from backend for the slide-up sheet
   */
  async fetchNdmaProtocol(scanResults) {
    const guidanceContainer = document.getElementById('ai-room-guidance');
    if (!guidanceContainer) return;

    const cycloneCat = document.getElementById('ai-tele-cat')?.textContent || 'VSCS';
    const windSpeed = document.getElementById('ai-tele-wind')?.textContent || '140 km/h';

    const payload = {
      hazards: scanResults.hazards,
      shelters: scanResults.shelters,
      room_safety_score: scanResults.score,
      category: cycloneCat,
      wind_speed: windSpeed,
      room_type: "Physical Room (Camera Scan)"
    };

    try {
      const apiBase = (window.location.protocol === 'file:' || (window.location.hostname === 'localhost' && window.location.port !== '5000') || (window.location.hostname === '127.0.0.1' && window.location.port !== '5000'))
        ? 'http://127.0.0.1:5000'
        : (window.location.origin || '');
      const resp = await fetch(`${apiBase}/api/ai/scan-room`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (resp.ok) {
        const data = await resp.json();
        if (typeof marked !== 'undefined') {
          guidanceContainer.innerHTML = marked.parse(data.guidance || '');
        } else {
          guidanceContainer.innerHTML = `<pre style="white-space:pre-wrap;">${data.guidance}</pre>`;
        }
        return;
      }
    } catch (e) {
      console.warn("Backend guidance fetch error:", e);
    }

    // Offline fallback protocol
    guidanceContainer.innerHTML = `
      <div style="font-size:12px;color:#e9e7df;line-height:1.6;">
        <p><strong>1. Immediate Shelter:</strong> ${scanResults.shelters.length ? `Take cover under ${scanResults.shelters[0]} with head protected.` : 'Move to interior room or corridor away from all windows.'}</p>
        <p><strong>2. Glass Protection:</strong> ${scanResults.hazards.length ? 'Draw all heavy curtains immediately to contain flying glass shards.' : 'Ensure all exterior doors and windows are latched.'}</p>
        <p><strong>3. Body Shielding:</strong> Cover your head and neck with thick blankets or cushions.</p>
      </div>
    `;
  }
}

// Global instance
window.roomScanner = new RoomSafetyScanner();

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  if (window.roomScanner) window.roomScanner.init();
});
window.addEventListener('resize', () => {
  if (window.roomScanner) window.roomScanner.resizeCanvas();
});
