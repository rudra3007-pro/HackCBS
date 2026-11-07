"""
CycloSense — Map / GIS Routes
Exposes geographic data for the Leaflet dashboard.

Endpoints
---------
GET  /api/map/track/<cyclone_id>   – Return predicted track as GeoJSON LineString
POST /api/map/impact               – Return risk-zone GeoJSON from forecast + intensity
GET  /api/map/basins               – Return Indian Ocean basin boundary GeoJSON
"""

import logging
import math

from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)
map_bp = Blueprint("map", __name__, url_prefix="/api/map")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _uncertainty_radius_km(hours: int) -> float:
    """
    Approximate uncertainty cone radius at a given forecast horizon.
    Grows linearly — fine-tuned from Model 3 multi-step errors.
    """
    error_map = {3: 130, 6: 160, 12: 240, 24: 400}
    if hours in error_map:
        return float(error_map[hours])
    # Linear interpolation for other horizons
    return 130.0 + (hours / 24.0) * (400.0 - 130.0)


def _km_to_deg(km: float) -> float:
    """Rough conversion: 1 degree ≈ 111 km."""
    return km / 111.0


def _intensity_to_risk(category: str) -> str:
    """Map IMD category to risk level."""
    mapping = {
        "D":    "LOW",
        "DD":   "LOW",
        "CS":   "MODERATE",
        "SCS":  "HIGH",
        "VSCS": "VERY HIGH",
    }
    return mapping.get(category, "UNKNOWN")


def _intensity_to_color(risk: str) -> str:
    colors = {
        "LOW":       "#2ecc71",
        "MODERATE":  "#f1c40f",
        "HIGH":      "#e67e22",
        "VERY HIGH": "#e74c3c",
        "UNKNOWN":   "#95a5a6",
    }
    return colors.get(risk, "#95a5a6")


def _haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate Great Circle distance between two points on Earth in kilometres."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 2)


# ──────────────────────────────────────────────────────────────────────────────
# Cyclone Shelter Database (Multi-Purpose Cyclone Shelters & Safe Havens)
# ──────────────────────────────────────────────────────────────────────────────
SHELTER_DATABASE = [
    # ── Odisha (Bay of Bengal) ────────────────────────────────────────────────
    {
        "id": "od_puri_01",
        "name": "Puri Model Multi-Purpose Cyclone Shelter (ODRRF-1)",
        "type": "Multi-Purpose Cyclone Shelter",
        "state": "Odisha", "district": "Puri",
        "lat": 19.8085, "lon": 85.8256,
        "elevation_m": 16.5, "capacity": 1800, "surge_safe": True,
        "facilities": ["Backup Solar Inverter", "Purified RO Water (5,000L)", "First Aid Emergency Kit", "Helipad Landing Ground", "Community Kitchen"],
        "contact": "06752-223400 / 1077",
        "address": "Near VIP Road, Sea Beach Road, Puri"
    },
    {
        "id": "od_puri_02",
        "name": "Brahmagiri Cyclone Relief Shelter & Community High School",
        "type": "Coastal Elevated School / Relief Center",
        "state": "Odisha", "district": "Puri",
        "lat": 19.8012, "lon": 85.6792,
        "elevation_m": 14.0, "capacity": 1200, "surge_safe": True,
        "facilities": ["Emergency Generator", "Overhead Drinking Water Tank", "Separate Women's Dormitory"],
        "contact": "06752-243122 / 1077",
        "address": "Block Headquarters, Brahmagiri"
    },
    {
        "id": "od_paradip_01",
        "name": "Paradip Port Central Cyclone Refuge & Disaster Hub",
        "type": "Reinforced Disaster Safe Haven",
        "state": "Odisha", "district": "Jagatsinghpur",
        "lat": 20.2986, "lon": 86.6714,
        "elevation_m": 18.2, "capacity": 2500, "surge_safe": True,
        "facilities": ["Heavy Industrial Genset", "Medical Trauma Care Unit", "Satellite HAM Radio Phone", "Decontamination Bay"],
        "contact": "06722-222144 / 1077",
        "address": "Port Trust Township, Gate No. 2, Paradip"
    },
    {
        "id": "od_balasore_01",
        "name": "Chandipur Coastal MPCS Shelter Center",
        "type": "Multi-Purpose Cyclone Shelter",
        "state": "Odisha", "district": "Balasore",
        "lat": 21.4682, "lon": 87.0195,
        "elevation_m": 12.8, "capacity": 1500, "surge_safe": True,
        "facilities": ["Solar Power Backup", "Water Treatment Filter", "Disaster Management Stockpile"],
        "contact": "06782-262100 / 1077",
        "address": "Main Marine Road, Chandipur"
    },
    {
        "id": "od_ganjam_01",
        "name": "Gopalpur-on-Sea High-Elevation Cyclone Shelter",
        "type": "Reinforced Coastal Shelter",
        "state": "Odisha", "district": "Ganjam",
        "lat": 19.2612, "lon": 84.9085,
        "elevation_m": 22.0, "capacity": 1600, "surge_safe": True,
        "facilities": ["High-Elevation Storm Surge Proofing", "Full Diesel Genset", "First Aid Ward"],
        "contact": "06811-282200 / 1077",
        "address": "Lighthouse Hill Road, Gopalpur"
    },

    # ── West Bengal (Sundarbans & Coast) ───────────────────────────────────────
    {
        "id": "wb_digha_01",
        "name": "New Digha Multi-Purpose Cyclone Center (MPCS-3)",
        "type": "Multi-Purpose Cyclone Shelter",
        "state": "West Bengal", "district": "Purba Medinipur",
        "lat": 21.6266, "lon": 87.5074,
        "elevation_m": 15.0, "capacity": 2000, "surge_safe": True,
        "facilities": ["Standby Diesel Power", "Emergency Water Plant", "Ambulance Station", "Sanitation Facility"],
        "contact": "03220-266222 / 1077",
        "address": "Opposite Science Centre, New Digha"
    },
    {
        "id": "wb_sagar_01",
        "name": "Sagar Island Central Gangasagar Safe Haven",
        "type": "Reinforced Flood/Cyclone Shelter",
        "state": "West Bengal", "district": "South 24 Parganas",
        "lat": 21.6495, "lon": 88.0784,
        "elevation_m": 11.5, "capacity": 3000, "surge_safe": True,
        "facilities": ["Mega Community Kitchen", "Multi-Tier Bunk Beds", "Life Jackets & Boat Stash", "Radio Beacon"],
        "contact": "033-24552000 / 1077",
        "address": "Pilgrim Centre Complex, Gangasagar"
    },
    {
        "id": "wb_kakdwip_01",
        "name": "Kakdwip Sub-Divisional Emergency Shelter Hospital",
        "type": "Hospital Disaster Relief Compound",
        "state": "West Bengal", "district": "South 24 Parganas",
        "lat": 21.8763, "lon": 88.1884,
        "elevation_m": 13.0, "capacity": 1400, "surge_safe": True,
        "facilities": ["ICU & Surgical Support", "Power Inverter Grid", "Oxygen Reserve Tanks"],
        "contact": "03210-255300 / 1077",
        "address": "NH-117, Hospital More, Kakdwip"
    },

    # ── Andhra Pradesh ────────────────────────────────────────────────────────
    {
        "id": "ap_vizag_01",
        "name": "Visakhapatnam RK Beach Elevated Shelter & Indoor Stadium",
        "type": "Elevated Community Shelter",
        "state": "Andhra Pradesh", "district": "Visakhapatnam",
        "lat": 17.7126, "lon": 83.3182,
        "elevation_m": 24.5, "capacity": 3500, "surge_safe": True,
        "facilities": ["Mass Capacity Hall", "Central High-Power Backup", "Emergency Communication Post"],
        "contact": "0891-2560000 / 1077",
        "address": "Beach Road, Pandurangapuram, Visakhapatnam"
    },
    {
        "id": "ap_kakinada_01",
        "name": "Kakinada Marine Cyclone Relief Center",
        "type": "Multi-Purpose Cyclone Shelter",
        "state": "Andhra Pradesh", "district": "Kakinada",
        "lat": 16.9891, "lon": 82.2475,
        "elevation_m": 12.0, "capacity": 1800, "surge_safe": True,
        "facilities": ["Solar Pump Water System", "Fishermen Evacuation Base", "First Aid Room"],
        "contact": "0884-2361000 / 1077",
        "address": "Port Road, Suryaraopeta, Kakinada"
    },
    {
        "id": "ap_machili_01",
        "name": "Machilipatnam Coastal Cyclone Shelter & Govt College",
        "type": "Elevated Institutional Shelter",
        "state": "Andhra Pradesh", "district": "Krishna",
        "lat": 16.1875, "lon": 81.1389,
        "elevation_m": 10.5, "capacity": 1500, "surge_safe": True,
        "facilities": ["Overhead Surge Ramp", "Emergency Food Stock", "Drinking Water Supply"],
        "contact": "08672-252100 / 1077",
        "address": "Koneru Center, Machilipatnam"
    },

    # ── Tamil Nadu ────────────────────────────────────────────────────────────
    {
        "id": "tn_chennai_01",
        "name": "Marina Coastal Flood & Cyclone Shelter (Greater Chennai Corp)",
        "type": "Reinforced Municipal Shelter",
        "state": "Tamil Nadu", "district": "Chennai",
        "lat": 13.0489, "lon": 80.2825,
        "elevation_m": 14.0, "capacity": 2200, "surge_safe": True,
        "facilities": ["24/7 Control Room", "Cooked Meal Distribution", "Medical Health Officer on Duty"],
        "contact": "044-25619206 / 1913",
        "address": "Kamarajar Salai, Near Light House, Chennai"
    },
    {
        "id": "tn_cuddalore_01",
        "name": "Cuddalore Old Town High-Ramp Cyclone Shelter",
        "type": "Multi-Purpose Cyclone Shelter",
        "state": "Tamil Nadu", "district": "Cuddalore",
        "lat": 11.7480, "lon": 79.7714,
        "elevation_m": 13.5, "capacity": 1600, "surge_safe": True,
        "facilities": ["High-Level Storm Surge Barrier", "Ramp Access for Disabled/Elderly", "Backup Generator"],
        "contact": "04142-220000 / 1077",
        "address": "Silver Beach Road, Devanampattinam, Cuddalore"
    },

    # ── Gujarat (Arabian Sea) ──────────────────────────────────────────────────
    {
        "id": "gj_veraval_01",
        "name": "Veraval Somnath Coastal Emergency Shelter Camp",
        "type": "Multi-Purpose Cyclone Shelter",
        "state": "Gujarat", "district": "Gir Somnath",
        "lat": 20.9077, "lon": 70.3667,
        "elevation_m": 19.0, "capacity": 2000, "surge_safe": True,
        "facilities": ["Reinforced Concrete Structure", "Solar Storage Batteries", "Emergency Drinking Water Depot"],
        "contact": "02876-240000 / 1077",
        "address": "Bypass Highway, Near Somnath Railway Station, Veraval"
    },
    {
        "id": "gj_porbandar_01",
        "name": "Porbandar Marine Fishery Port Cyclone Shelter",
        "type": "Marine Cyclone Safe Haven",
        "state": "Gujarat", "district": "Porbandar",
        "lat": 21.6417, "lon": 69.6293,
        "elevation_m": 16.0, "capacity": 1700, "surge_safe": True,
        "facilities": ["Boat Crew Relief Hall", "First Aid Ward", "Satellite Communication Desk"],
        "contact": "0286-2240000 / 1077",
        "address": "Subhash Nagar Beach Road, Porbandar"
    },
    {
        "id": "gj_kandla_01",
        "name": "Deendayal Port Trust Cyclone Shelter & Community Center",
        "type": "Port Safety Shelter",
        "state": "Gujarat", "district": "Kutch",
        "lat": 23.0033, "lon": 70.2186,
        "elevation_m": 15.5, "capacity": 2200, "surge_safe": True,
        "facilities": ["Industrial Generator", "CCTV Surveillance", "Medical Clinic"],
        "contact": "02836-238000 / 1077",
        "address": "Port Colony, Kandla, Gandhidham"
    },

    # ── Maharashtra (Arabian Sea) ─────────────────────────────────────────────
    {
        "id": "mh_mumbai_01",
        "name": "Worli Elevated Disaster Shelter & Relief Complex",
        "type": "Municipal Disaster Center",
        "state": "Maharashtra", "district": "Mumbai City",
        "lat": 19.0178, "lon": 72.8180,
        "elevation_m": 22.0, "capacity": 3000, "surge_safe": True,
        "facilities": ["MCGM Disaster Control Terminal", "Emergency Doctors Team", "Standby Generators"],
        "contact": "022-22694725 / 1916",
        "address": "Khan Abdul Ghaffar Khan Road, Worli, Mumbai"
    },
    {
        "id": "mh_alibaug_01",
        "name": "Alibaug Coastal Taluka Cyclone Shelter",
        "type": "Multi-Purpose Cyclone Shelter",
        "state": "Maharashtra", "district": "Raigad",
        "lat": 18.6414, "lon": 72.8722,
        "elevation_m": 14.0, "capacity": 1500, "surge_safe": True,
        "facilities": ["Drinking Water Purification", "Solar Lighting Grid", "Community Kitchen"],
        "contact": "02141-222001 / 1077",
        "address": "Varsoli Beach Road, Alibaug"
    }
]


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────

@map_bp.post("/track")
def track_geojson():
    """
    Convert a forecast result into a GeoJSON FeatureCollection for Leaflet.

    Request JSON:
    {
      "current": {"lat": float, "lon": float},
      "forecast": [
        {"hours": 3,  "lat": ..., "lon": ..., "wind_speed": ...},
        {"hours": 6,  ...},
        {"hours": 12, ...},
        {"hours": 24, ...}
      ],
      "category": "VSCS"   // optional — from Model 2
    }

    Response: GeoJSON FeatureCollection with:
      - LineString of the predicted track
      - Point markers for each forecast position (with uncertainty radius)
    """
    body = request.get_json(silent=True)
    if not body or "forecast" not in body or "current" not in body:
        return jsonify({"error": "JSON with 'current' and 'forecast' required."}), 400

    current  = body["current"]
    forecast = body["forecast"]
    category = body.get("category", "CS")
    risk     = _intensity_to_risk(category)
    color    = _intensity_to_color(risk)

    # Build coordinate list: current → forecast points
    coords = [[current["lon"], current["lat"]]]
    coords += [[pt["lon"], pt["lat"]] for pt in forecast]

    features = []

    # ── Main track LineString ──────────────────────────────────────────────
    features.append({
        "type": "Feature",
        "geometry": {
            "type":        "LineString",
            "coordinates": coords,
        },
        "properties": {
            "type":     "predicted_track",
            "category": category,
            "risk":     risk,
            "color":    color,
            "dash":     "dashed",
        },
    })

    # ── Current position marker ────────────────────────────────────────────
    features.append({
        "type": "Feature",
        "geometry": {
            "type":        "Point",
            "coordinates": [current["lon"], current["lat"]],
        },
        "properties": {
            "type":       "current_position",
            "label":      "Current Position",
            "category":   category,
            "risk":       risk,
            "color":      color,
            "hours":      0,
        },
    })

    # ── Forecast point markers + uncertainty circles ───────────────────────
    for pt in forecast:
        radius_km  = _uncertainty_radius_km(pt["hours"])
        radius_deg = _km_to_deg(radius_km)

        features.append({
            "type": "Feature",
            "geometry": {
                "type":        "Point",
                "coordinates": [pt["lon"], pt["lat"]],
            },
            "properties": {
                "type":             "forecast_point",
                "label":            f"+{pt['hours']}h",
                "hours":            pt["hours"],
                "wind_speed_kts":   round(pt["wind_speed"] * 0.539957, 1),  # km/h → kts
                "wind_speed_kmh":   pt["wind_speed"],
                "uncertainty_km":   radius_km,
                "uncertainty_deg":  round(radius_deg, 4),
                "color":            color,
            },
        })

    return jsonify({
        "type":     "FeatureCollection",
        "features": features,
        "meta": {
            "category":   category,
            "risk_level": risk,
            "color":      color,
        }
    }), 200


@map_bp.post("/impact")
def impact_zones():
    """
    Generate a simple impact risk zone GeoJSON around the forecast track.

    Request JSON:
    {
      "forecast": [ {"lat": ..., "lon": ..., "wind_speed": ..., "hours": ...} ],
      "category": "SCS"
    }

    Response: GeoJSON FeatureCollection with colour-coded impact polygons
    (approximated as bounding boxes around each forecast point).
    """
    body = request.get_json(silent=True)
    if not body or "forecast" not in body:
        return jsonify({"error": "JSON with 'forecast' required."}), 400

    forecast = body["forecast"]
    category = body.get("category", "CS")
    risk     = _intensity_to_risk(category)
    color    = _intensity_to_color(risk)

    features = []
    for pt in forecast:
        radius_deg = _km_to_deg(_uncertainty_radius_km(pt["hours"]))
        lat, lon   = pt["lat"], pt["lon"]

        # Simple bounding-box polygon for the impact zone
        polygon_coords = [[
            [lon - radius_deg, lat - radius_deg],
            [lon + radius_deg, lat - radius_deg],
            [lon + radius_deg, lat + radius_deg],
            [lon - radius_deg, lat + radius_deg],
            [lon - radius_deg, lat - radius_deg],
        ]]

        features.append({
            "type": "Feature",
            "geometry": {
                "type":        "Polygon",
                "coordinates": polygon_coords,
            },
            "properties": {
                "type":       "impact_zone",
                "hours":      pt["hours"],
                "risk":       risk,
                "color":      color,
                "opacity":    0.15,
                "wind_speed": pt["wind_speed"],
            },
        })

    return jsonify({
        "type":     "FeatureCollection",
        "features": features,
        "meta":     {"risk_level": risk, "category": category},
    }), 200


@map_bp.get("/basins")
def basins():
    """
    Return a simple GeoJSON bounding box for the North Indian Ocean monitoring domain.
    Clients use this to set the initial Leaflet map view.
    """
    domain = {
        "lat_min":  0.0,  "lat_max":  35.0,
        "lon_min": 40.0,  "lon_max": 100.0,
        "centre":  {"lat": 15.0, "lon": 80.0},
        "zoom":    5,
    }
    return jsonify({"domain": domain}), 200


@map_bp.get("/shelters")
def list_shelters():
    """
    Return all registered cyclone shelters, optionally filtered by state or district.
    """
    state_filter = request.args.get("state", "").strip().lower()
    district_filter = request.args.get("district", "").strip().lower()

    results = []
    for s in SHELTER_DATABASE:
        if state_filter and s["state"].lower() != state_filter:
            continue
        if district_filter and s["district"].lower() != district_filter:
            continue
        results.append(s)

    return jsonify({
        "status": "success",
        "total": len(results),
        "shelters": results
    }), 200


@map_bp.post("/nearest-shelters")
def find_nearest_shelters():
    """
    Given user's current GPS location (lat, lon), return nearest safe cyclone shelters
    sorted by Geodesic distance (Haversine formula), with estimated walking and drive times.

    Request JSON:
    {
      "lat": 19.81,
      "lon": 85.83,
      "limit": 5,           // optional, default 5
      "max_radius_km": 250  // optional, default 250
    }
    """
    body = request.get_json(silent=True) or {}
    user_lat = body.get("lat")
    user_lon = body.get("lon")

    if user_lat is None or user_lon is None:
        return jsonify({"error": "Missing 'lat' or 'lon' in request body."}), 400

    try:
        user_lat = float(user_lat)
        user_lon = float(user_lon)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid coordinates format."}), 400

    limit = int(body.get("limit", 5))
    max_radius_km = float(body.get("max_radius_km", 250.0))

    enriched_shelters = []
    for s in SHELTER_DATABASE:
        dist_km = _haversine_distance_km(user_lat, user_lon, s["lat"], s["lon"])
        if dist_km <= max_radius_km:
            item = dict(s)
            item["distance_km"] = dist_km
            item["walking_time_mins"] = int(dist_km * 12)  # ~5 km/h
            item["drive_time_mins"] = max(2, int(dist_km * 2.5))  # ~25 km/h in stormy weather
            item["nav_url"] = f"https://www.google.com/maps/dir/?api=1&destination={s['lat']},{s['lon']}"
            enriched_shelters.append(item)

    # Sort ascending by distance
    enriched_shelters.sort(key=lambda x: x["distance_km"])

    top_shelters = enriched_shelters[:limit]
    nearest = top_shelters[0] if top_shelters else None

    # GeoJSON FeatureCollection representation for direct Leaflet consumption
    features = []
    # User location point
    features.append({
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [user_lon, user_lat]
        },
        "properties": {
            "type": "user_location",
            "label": "Your Current Location"
        }
    })

    # Shelter points
    for s in top_shelters:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [s["lon"], s["lat"]]
            },
            "properties": {
                "type": "cyclone_shelter",
                "id": s["id"],
                "name": s["name"],
                "distance_km": s["distance_km"],
                "capacity": s["capacity"],
                "elevation_m": s["elevation_m"],
                "contact": s["contact"],
                "nav_url": s["nav_url"]
            }
        })

    return jsonify({
        "status": "success",
        "user_coords": {"lat": user_lat, "lon": user_lon},
        "nearest_shelter": nearest,
        "shelters": top_shelters,
        "total_in_radius": len(enriched_shelters),
        "geojson": {
            "type": "FeatureCollection",
            "features": features
        }
    }), 200


# ── Server-side Nominatim Geocoding Proxy (Compliant with OSM Policy) ────────
_geocode_cache = {}

@map_bp.get("/geocode")
def geocode():
    """
    Server-side proxy for Nominatim geocoding.
    Complies with Nominatim usage policy:
      - Sets explicit identifying User-Agent
      - Limits results and caches responses in memory
    """
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Missing query parameter 'q'."}), 400

    cache_key = query.lower()
    if cache_key in _geocode_cache:
        return jsonify(_geocode_cache[cache_key]), 200

    try:
        import requests
        url = "https://nominatim.openstreetmap.org/search"
        headers = {
            "User-Agent": "CycloSense/2.0 (contact@cyclosense.org)"
        }
        params = {
            "format": "json",
            "q": query,
            "limit": 1
        }
        resp = requests.get(url, headers=headers, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if len(_geocode_cache) < 500:
                _geocode_cache[cache_key] = data
            return jsonify(data), 200
        return jsonify({"error": "Geocoding service error"}), resp.status_code
    except Exception as e:
        logger.warning("Geocoding lookup failed: %s", e)
        return jsonify({"error": "Geocoding request failed"}), 500
