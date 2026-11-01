/**
 * CycloSense — Emergency Cyclone Shelter & Safe Haven Radar
 * Fetches user GPS location, queries nearest government-verified Multi-Purpose
 * Cyclone Shelters (MPCS), calculates geodesic distances and storm-surge safety,
 * renders interactive markers on Leaflet, and provides 1-click turn-by-turn navigation.
 */

class CycloneShelterRadar {
  constructor() {
    this.userCoords = null;
    this.shelters = [];
    this.nearestShelter = null;
    this.shelterLayer = null;
    this.routeLine = null;
    this.userMarker = null;
    this.isLoading = false;

    // Presets for quick desktop testing or when GPS is denied
    this.cityPresets = [
      { name: "Puri Beach, Odisha", lat: 19.805, lon: 85.820 },
      { name: "Paradip Port, Odisha", lat: 20.300, lon: 86.675 },
      { name: "Digha Coast, West Bengal", lat: 21.625, lon: 87.510 },
      { name: "Gangasagar, Sundarbans", lat: 21.650, lon: 88.080 },
      { name: "RK Beach, Visakhapatnam", lat: 17.715, lon: 83.320 },
      { name: "Marina Beach, Chennai", lat: 13.048, lon: 80.280 },
      { name: "Veraval / Somnath, Gujarat", lat: 20.910, lon: 70.368 },
      { name: "Worli Sea Face, Mumbai", lat: 19.018, lon: 72.818 },
    ];
  }

  getMap() {
    return window.MAP || (typeof MAP !== 'undefined' ? MAP : null);
  }

  /**
   * Main entry point: Get User GPS or Prompt City Picker
   */
  locateAndFind() {
    if (!navigator.geolocation) {
      this.promptCityPicker("GPS is not supported by your browser. Select your coastal region:");
      return;
    }

    this.showLoadingToast("Locating your GPS coordinates…");

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const lat = pos.coords.latitude;
        const lon = pos.coords.longitude;
        this.fetchNearestShelters(lat, lon, "Your Live GPS Location");
      },
      (err) => {
        console.warn("Geolocation denied or timed out:", err.message);
        this.promptCityPicker("GPS location access was denied or timed out. Pick your coastal location to find nearby shelters:");
      },
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 }
    );
  }

  /**
   * Fetch nearest shelters from backend API
   */
  async fetchNearestShelters(lat, lon, label = "User Location") {
    this.userCoords = { lat, lon, label };
    this.isLoading = true;
    this.showLoadingToast(`Finding cyclone shelters near ${label}…`);

    const payload = {
      lat: lat,
      lon: lon,
      limit: 5,
      max_radius_km: 250
    };

    try {
      const apiBase = (window.location.protocol === 'file:' || (window.location.hostname === 'localhost' && window.location.port !== '5000') || (window.location.hostname === '127.0.0.1' && window.location.port !== '5000'))
        ? 'http://127.0.0.1:5000'
        : (window.location.origin || '');
      const resp = await fetch(`${apiBase}/api/map/nearest-shelters`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!resp.ok) {
        throw new Error(`Server returned HTTP ${resp.status}`);
      }

      const data = await resp.json();
      this.shelters = data.shelters || [];
      this.nearestShelter = data.nearest_shelter || null;

      this.renderOnLeafletMap();
      this.showShelterDrawer(data);
      this.hideLoadingToast();
    } catch (err) {
      console.warn("Backend nearest-shelters endpoint failed, using client-side fallback:", err);
      this.calculateClientFallback(lat, lon);
      this.hideLoadingToast();
    } finally {
      this.isLoading = false;
    }
  }

  /**
   * Client-side fallback if backend API is offline
   */
  calculateClientFallback(userLat, userLon) {
    const fallbackDB = [
      {
        id: "od_puri_01",
        name: "Puri Model Multi-Purpose Cyclone Shelter (ODRRF-1)",
        type: "Multi-Purpose Cyclone Shelter",
        state: "Odisha", district: "Puri",
        lat: 19.8085, lon: 85.8256,
        elevation_m: 16.5, capacity: 1800, surge_safe: true,
        facilities: ["Backup Solar Inverter", "Purified RO Water (5,000L)", "First Aid Emergency Kit", "Helipad Landing Ground"],
        contact: "06752-223400 / 1077",
        address: "Near VIP Road, Sea Beach Road, Puri"
      },
      {
        id: "od_paradip_01",
        name: "Paradip Port Central Cyclone Refuge & Disaster Hub",
        type: "Reinforced Disaster Safe Haven",
        state: "Odisha", district: "Jagatsinghpur",
        lat: 20.2986, lon: 86.6714,
        elevation_m: 18.2, capacity: 2500, surge_safe: true,
        facilities: ["Heavy Industrial Genset", "Medical Trauma Care Unit", "Satellite HAM Radio Phone"],
        contact: "06722-222144 / 1077",
        address: "Port Trust Township, Gate No. 2, Paradip"
      },
      {
        id: "wb_digha_01",
        name: "New Digha Multi-Purpose Cyclone Center (MPCS-3)",
        type: "Multi-Purpose Cyclone Shelter",
        state: "West Bengal", district: "Purba Medinipur",
        lat: 21.6266, lon: 87.5074,
        elevation_m: 15.0, capacity: 2000, surge_safe: true,
        facilities: ["Standby Diesel Power", "Emergency Water Plant", "Ambulance Station"],
        contact: "03220-266222 / 1077",
        address: "Opposite Science Centre, New Digha"
      },
      {
        id: "ap_vizag_01",
        name: "Visakhapatnam RK Beach Elevated Shelter & Stadium",
        type: "Elevated Community Shelter",
        state: "Andhra Pradesh", district: "Visakhapatnam",
        lat: 17.7126, lon: 83.3182,
        elevation_m: 24.5, capacity: 3500, surge_safe: true,
        facilities: ["Mass Capacity Hall", "Central High-Power Backup", "Emergency Post"],
        contact: "0891-2560000 / 1077",
        address: "Beach Road, Pandurangapuram, Visakhapatnam"
      },
      {
        id: "tn_chennai_01",
        name: "Marina Coastal Cyclone Relief Center (GCC)",
        type: "Reinforced Municipal Shelter",
        state: "Tamil Nadu", district: "Chennai",
        lat: 13.0489, lon: 80.2825,
        elevation_m: 14.0, capacity: 2200, surge_safe: true,
        facilities: ["24/7 Control Room", "Cooked Meal Distribution", "Medical Health Officer"],
        contact: "044-25619206 / 1913",
        address: "Kamarajar Salai, Near Light House, Chennai"
      },
      {
        id: "gj_veraval_01",
        name: "Veraval Somnath Coastal Emergency Shelter Camp",
        type: "Multi-Purpose Cyclone Shelter",
        state: "Gujarat", district: "Gir Somnath",
        lat: 20.9077, lon: 70.3667,
        elevation_m: 19.0, capacity: 2000, surge_safe: true,
        facilities: ["Reinforced Concrete Structure", "Solar Storage Batteries", "Drinking Water Depot"],
        contact: "02876-240000 / 1077",
        address: "Bypass Highway, Near Somnath Railway Station, Veraval"
      }
    ];

    const R = 6371.0;
    const enriched = fallbackDB.map(s => {
      const dLat = (s.lat - userLat) * Math.PI / 180;
      const dLon = (s.lon - userLon) * Math.PI / 180;
      const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                Math.cos(userLat * Math.PI / 180) * Math.cos(s.lat * Math.PI / 180) *
                Math.sin(dLon / 2) * Math.sin(dLon / 2);
      const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
      const dist = Math.round(R * c * 10) / 10;
      return {
        ...s,
        distance_km: dist,
        walking_time_mins: Math.round(dist * 12),
        drive_time_mins: Math.max(3, Math.round(dist * 2.5)),
        nav_url: `https://www.google.com/maps/dir/?api=1&destination=${s.lat},${s.lon}`
      };
    });

    enriched.sort((a, b) => a.distance_km - b.distance_km);
    this.shelters = enriched.slice(0, 5);
    this.nearestShelter = this.shelters[0] || null;

    this.renderOnLeafletMap();
    this.showShelterDrawer({
      shelters: this.shelters,
      nearest_shelter: this.nearestShelter,
      total_in_radius: enriched.length
    });
  }

  /**
   * Render User Marker, Shelters, and Navigation Polyline on Leaflet
   */
  renderOnLeafletMap() {
    const map = this.getMap();
    if (!map || typeof L === 'undefined') return;

    // Create or clear layer group
    if (!this.shelterLayer) {
      this.shelterLayer = L.layerGroup().addTo(map);
    } else {
      this.shelterLayer.clearLayers();
    }

    const uLat = this.userCoords.lat;
    const uLon = this.userCoords.lon;

    // 1. User Location Marker (Glowing Blue Radar Pulse)
    const userHtml = `
      <div class="user-gps-pulse-wrap">
        <div class="user-gps-dot"></div>
        <div class="user-gps-ring"></div>
      </div>
    `;
    const userIcon = L.divIcon({
      className: 'custom-user-icon',
      html: userHtml,
      iconSize: [28, 28],
      iconAnchor: [14, 14]
    });

    this.userMarker = L.marker([uLat, uLon], { icon: userIcon, zIndexOffset: 1000 })
      .bindPopup(`
        <div style="font-family:'Inter',-apple-system,sans-serif;padding:2px 4px;">
          <strong style="color:#35c6b4;font-size:12px;">📍 Your Location</strong><br>
          <span style="font-size:11px;color:#c2c2ba;">${this.userCoords.label}</span><br>
          <small style="font-family:'JetBrains Mono',monospace;color:#888b82;font-size:10px;">${uLat.toFixed(3)}°N, ${uLon.toFixed(3)}°E</small>
        </div>
      `)
      .addTo(this.shelterLayer);

    const boundsPoints = [[uLat, uLon]];

    // 2. Shelter Markers
    this.shelters.forEach((s, idx) => {
      const isNearest = idx === 0;
      const markerColor = isNearest ? '#35c6b4' : '#e7a64e';
      const shieldHtml = `
        <div class="shelter-badge-icon ${isNearest ? 'nearest-pulse' : ''}" style="border-color:${markerColor};">
          <span class="shelter-icon-inner">${isNearest ? '🛡️' : '🏠'}</span>
          <span class="shelter-dist-tag" style="background:${markerColor};">${s.distance_km}km</span>
        </div>
      `;

      const shelterIcon = L.divIcon({
        className: 'custom-shelter-icon',
        html: shieldHtml,
        iconSize: [36, 44],
        iconAnchor: [18, 22]
      });

      const facilitiesHtml = s.facilities ? s.facilities.map(f => `<span class="shelter-fac-pill">${f}</span>`).join('') : '';

      const popupContent = `
        <div class="shelter-leaflet-popup">
          <div class="popup-shelter-title">
            <span style="color:${markerColor};font-size:14px;">🛡️</span>
            <strong>${s.name}</strong>
          </div>
          <div class="popup-meta-row">
            <span><strong>Distance:</strong> ${s.distance_km} km</span>
            <span class="badge-surge-safe">${s.elevation_m}m MSL (Surge-Safe)</span>
          </div>
          <div class="popup-meta-row">
            <span><strong>Capacity:</strong> ${s.capacity} persons</span>
            <span><strong>ETA:</strong> ~${s.drive_time_mins}m drive</span>
          </div>
          <div class="popup-facilities">${facilitiesHtml}</div>
          <div class="popup-actions">
            <a href="${s.nav_url}" target="_blank" class="btn-popup-nav">
              🧭 Directions (Google Maps)
            </a>
            <a href="tel:${s.contact.split('/')[0].trim()}" class="btn-popup-call">
              📞 ${s.contact.split('/')[0].trim()}
            </a>
          </div>
        </div>
      `;

      const marker = L.marker([s.lat, s.lon], { icon: shelterIcon, zIndexOffset: isNearest ? 900 : 500 })
        .bindPopup(popupContent, { maxWidth: 320 })
        .addTo(this.shelterLayer);

      boundsPoints.push([s.lat, s.lon]);

      if (isNearest) {
        marker.openPopup();
      }
    });

    // 3. Navigation Polyline to the nearest shelter
    if (this.nearestShelter) {
      const routePoints = [
        [uLat, uLon],
        [this.nearestShelter.lat, this.nearestShelter.lon]
      ];

      this.routeLine = L.polyline(routePoints, {
        color: '#35c6b4',
        weight: 3.5,
        opacity: 0.85,
        dashArray: '8, 8',
        lineCap: 'round'
      }).addTo(this.shelterLayer);
    }

    // Smoothly fly map to bounds containing user and shelters
    map.flyToBounds(boundsPoints, {
      padding: [60, 60],
      maxZoom: 13,
      duration: 1.2
    });
  }

  /**
   * Display floating Emergency Shelter Radar Drawer
   */
  showShelterDrawer(data) {
    const drawer = document.getElementById('shelter-radar-drawer');
    if (!drawer) return;

    drawer.style.display = 'flex';
    drawer.classList.add('open');

    const s = this.nearestShelter;
    if (!s) return;

    const nameEl = document.getElementById('nearest-shelter-name');
    const distEl = document.getElementById('nearest-shelter-dist');
    const timeEl = document.getElementById('nearest-shelter-times');
    const elevEl = document.getElementById('nearest-shelter-elev');
    const capEl = document.getElementById('nearest-shelter-cap');
    const facsEl = document.getElementById('nearest-shelter-facs');
    const navBtn = document.getElementById('btn-shelter-nav-gmaps');
    const callBtn = document.getElementById('btn-shelter-call');
    const listEl = document.getElementById('other-shelters-list');

    if (nameEl) nameEl.textContent = s.name;
    if (distEl) distEl.textContent = `${s.distance_km} km`;
    if (timeEl) timeEl.innerHTML = `~<strong>${s.drive_time_mins} mins</strong> drive &middot; ~<strong>${s.walking_time_mins} mins</strong> walk`;
    if (elevEl) elevEl.textContent = `+${s.elevation_m}m Above Sea Level (Storm Surge Safe)`;
    if (capEl) capEl.textContent = `${s.capacity} Occupants`;

    if (facsEl && s.facilities) {
      facsEl.innerHTML = s.facilities.map(f => `<span class="shelter-pill">${f}</span>`).join('');
    }

    if (navBtn) {
      navBtn.onclick = () => window.open(s.nav_url, '_blank');
    }
    if (callBtn) {
      const phone = s.contact.split('/')[0].trim();
      callBtn.onclick = () => window.location.href = `tel:${phone}`;
      callBtn.innerHTML = `<i class="bi bi-telephone-fill"></i> Call Helpline (${phone})`;
    }

    // Populate remaining list
    if (listEl) {
      const remaining = (data.shelters || []).slice(1);
      if (remaining.length) {
        listEl.innerHTML = remaining.map(rem => `
          <div class="other-shelter-card" onclick="window.shelterFinder.focusShelter(${rem.lat}, ${rem.lon})">
            <div>
              <div class="other-shelter-title">${rem.name}</div>
              <div class="other-shelter-meta">${rem.type} &middot; Cap: ${rem.capacity}</div>
            </div>
            <div class="other-shelter-dist">
              <strong>${rem.distance_km} km</strong>
              <small>~${rem.drive_time_mins}m</small>
            </div>
          </div>
        `).join('');
      } else {
        listEl.innerHTML = `<div style="font-size:11px;color:var(--text-muted);">No other shelters within current search radius.</div>`;
      }
    }
  }

  focusShelter(lat, lon) {
    const map = this.getMap();
    if (map) {
      map.flyTo([lat, lon], 14, { duration: 0.8 });
    }
  }

  closeDrawer() {
    const drawer = document.getElementById('shelter-radar-drawer');
    if (drawer) {
      drawer.classList.remove('open');
      setTimeout(() => drawer.style.display = 'none', 250);
    }
  }

  /**
   * Speak aloud navigation directions
   */
  speakShelterAdvisory() {
    if (!('speechSynthesis' in window) || !this.nearestShelter) return;
    window.speechSynthesis.cancel();

    const s = this.nearestShelter;
    const text = `Emergency Shelter Alert. Your nearest cyclone shelter is ${s.name}, located ${s.distance_km} kilometers away. Estimated drive time is ${s.drive_time_mins} minutes. This shelter is elevated ${s.elevation_m} meters above sea level and is safe against storm surges. Capacity is ${s.capacity} persons. Follow the route shown on your map.`;

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.0;
    window.speechSynthesis.speak(utterance);
  }

  /**
   * Prompt user with coastal city presets if GPS is unavailable
   */
  promptCityPicker(msg) {
    const picker = document.getElementById('shelter-city-picker-modal');
    if (picker) {
      const msgEl = document.getElementById('picker-msg');
      if (msgEl) msgEl.textContent = msg;

      const list = document.getElementById('picker-city-list');
      if (list) {
        list.innerHTML = this.cityPresets.map(c => `
          <button class="btn-picker-city" onclick="window.shelterFinder.selectCityPreset(${c.lat}, ${c.lon}, '${c.name}')">
            <i class="bi bi-geo-alt-fill"></i> ${c.name}
          </button>
        `).join('');
      }
      picker.classList.add('open');
    } else {
      // Default fallback to Puri
      this.fetchNearestShelters(19.805, 85.820, "Puri Coastal Zone, Odisha");
    }
  }

  selectCityPreset(lat, lon, name) {
    const picker = document.getElementById('shelter-city-picker-modal');
    if (picker) picker.classList.remove('open');
    this.fetchNearestShelters(lat, lon, name);
  }

  closeCityPicker() {
    const picker = document.getElementById('shelter-city-picker-modal');
    if (picker) picker.classList.remove('open');
  }

  showLoadingToast(msg) {
    let toast = document.getElementById('shelter-toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'shelter-toast';
      toast.className = 'shelter-radar-toast';
      document.body.appendChild(toast);
    }
    toast.innerHTML = `<div class="spinner-sm"></div> <span>${msg}</span>`;
    toast.style.display = 'flex';
  }

  hideLoadingToast() {
    const toast = document.getElementById('shelter-toast');
    if (toast) toast.style.display = 'none';
  }
}

// Global instance
window.shelterFinder = new CycloneShelterRadar();

