"""
CycloSense — AI Action Planner & Cyclone Assistant Route
Powered by Groq API (Llama-3.3-70B / Llama-3.1-8B)

Endpoints
---------
GET  /api/ai/status   – Liveness & Groq API configuration status
POST /api/ai/ask      – Decision assistant query grounded in cyclone telemetry
"""

import os
import logging
from flask import Blueprint, request, jsonify
from app.utils.rate_limiter import rate_limit

logger = logging.getLogger(__name__)
ai_bp = Blueprint("ai", __name__, url_prefix="/api/ai")

DEFAULT_MODEL = "qwen/qwen3.8-27b"
FALLBACK_MODEL = "openai/gpt-oss-120b"


def _get_api_key() -> str:
    """Retrieve Groq API key strictly from server environment or backend/.env file."""
    # Check environment variable
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if key and key != "your_groq_api_key_here":
        return key

    # Absolute path to backend directory (ai.py -> routes -> app -> backend)
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    root_dir = os.path.dirname(backend_dir)

    candidate_paths = [
        os.path.join(backend_dir, ".env"),
        os.path.join(root_dir, ".env"),
        os.path.join(root_dir, "backend", ".env"),
        "backend/.env",
        ".env",
    ]

    for env_path in candidate_paths:
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("GROQ_API_KEY="):
                            val = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if val and val != "your_groq_api_key_here":
                                return val
            except Exception:
                pass

    return ""


def _build_system_prompt(role: str, context: dict) -> str:
    """Ground the LLM with live CycloSense model outputs and selected user role."""
    detected = context.get("cyclone_detected", False)
    category = context.get("category", "Unknown")
    confidence = context.get("confidence", 0)
    pos = context.get("current_position", {})
    lat = pos.get("lat") or context.get("lat", "Unknown")
    lon = pos.get("lon") or context.get("lon", "Unknown")
    wind_kmh = context.get("wind_speed_kmh") or context.get("wind_speed", "Unknown")
    risk_level = context.get("risk_level", "MODERATE")
    forecast = context.get("forecast", [])

    forecast_summary = ""
    if forecast:
        steps = []
        for pt in forecast:
            h = pt.get("hours")
            p_lat = pt.get("lat")
            p_lon = pt.get("lon")
            w = pt.get("wind_speed")
            steps.append(f"  • +{h}h: Lat {p_lat}°N, Lon {p_lon}°E, Wind: {w} km/h")
        forecast_summary = "\n".join(steps)
    else:
        forecast_summary = "  • No trajectory forecast loaded yet."

    role_guidelines = {
        "resident": (
            "Target audience: Coastal and inland residents. Focus on household safety, "
            "evacuation timelines, shelter locations, emergency supply kits (food, potable water, batteries), "
            "and immediate precautions against flooding, flying debris, and storm surges."
        ),
        "fisherman": (
            "Target audience: Fishermen, boat owners, and maritime operators. Emphasize total suspension "
            "of fishing operations, immediate return to harbour/shore, securing boats and fishing gear, "
            "monitoring wave heights and marine gale warnings."
        ),
        "port_operator": (
            "Target audience: Port, shipping, and coastal infrastructure authorities. Focus on berthing "
            "suspension, cargo crane lockdown, barge anchoring, vessel de-berthing, communication backup, "
            "and structural protection against gale-force winds and surges."
        ),
        "disaster_official": (
            "Target audience: NDRF, SDRF, district collectors, and emergency response teams. Provide high-level "
            "operational guidance: priority evacuation zones, hospital backup power readiness, deployment of rescue boats, "
            "resource pre-positioning along landfall corridors, and multi-agency coordination."
        ),
        "general": (
            "Target audience: General public and media. Provide clear, calm, authoritative cyclone summary, "
            "severity explanation, expected impacts, and verified emergency helplines advice."
        )
    }.get(role.lower(), "Target audience: General public. Provide authoritative, safety-first cyclone guidance.")

    prompt = f"""You are the CycloSense AI Action Planner & Decision Assistant, an expert meteorological emergency intelligence system for the North Indian Ocean basin (Bay of Bengal and Arabian Sea), compliant with India Meteorological Department (IMD) standards.

CURRENT CYCLOSENSE REAL-TIME TELEMETRY:
----------------------------------------
- Cyclone Detected: {detected}
- IMD Category: {category} (Confidence: {confidence*100:.1f}%)
- Current Center Position: {lat}°N, {lon}°E
- Estimated Surface Wind Speed: {wind_kmh} km/h
- Assessed Risk Level: {risk_level}
- Predicted Trajectory Horizons (LSTM Model 3):
{forecast_summary}

USER ROLE & PERSPECTIVE:
------------------------
{role_guidelines}

INSTRUCTIONS:
1. Always base your analysis and recommendations strictly on the live telemetry provided above.
2. Structure your response with clear Markdown headings, bullet points, and high-priority action items.
3. Include:
   - 🚨 **Current Situation & Threat Window**: Category severity and projected path.
   - 🎯 **Critical Immediate Actions**: 3-5 high-priority steps tailored to the user's role.
   - ⏱️ **Timeline & Landfall Precautions**: What to do right now vs. in the next 6-24 hours.
   - ⚠️ **Key Hazard Warnings**: Wind gust damage, storm surges, inland flooding, or communication outage.
4. Keep the tone calm, urgent, highly professional, and actionable. Do not speculate beyond meteorological consensus.
"""
    return prompt


@ai_bp.get("/status")
def ai_status():
    """Check if Groq API key is available and list supported models."""
    key = _get_api_key()
    return jsonify({
        "groq_configured": bool(key),
        "default_model": DEFAULT_MODEL,
        "available_models": [
            DEFAULT_MODEL,
            FALLBACK_MODEL,
            "mixtral-8x7b-32768",
            "gemma2-9b-it"
        ]
    }), 200


@ai_bp.post("/ask")
@rate_limit(max_per_minute=20)
def ask_ai():
    """
    Query the AI Action Planner / Cyclone Assistant.

    Request JSON:
    {
      "message": "What should residents in Odisha do right now?",
      "role": "resident" | "fisherman" | "port_operator" | "disaster_official" | "general",
      "context": {
         "cyclone_detected": true,
         "category": "VSCS",
         "confidence": 0.91,
         "lat": 14.2,
         "lon": 82.6,
         "wind_speed_kmh": 175,
         "forecast": [...],
         "risk_level": "VERY HIGH"
      },
      "api_key": "optional groq api key override",
      "model": "optional groq model name",
      "conversation_history": [ {"role": "user"|"assistant", "content": "..."} ]
    }
    """
    data = request.get_json(silent=True) or {}
    user_msg = data.get("message", "").strip()
    role = data.get("role", "general")
    context = data.get("context", {})
    model_name = data.get("model", DEFAULT_MODEL)
    history = data.get("conversation_history", [])

    api_key = _get_api_key()
    if not api_key:
        return jsonify({
            "error": "Groq API key not configured.",
            "instructions": (
                "Please provide your Groq API key in the request payload as 'api_key', "
                "or set the GROQ_API_KEY environment variable on the backend server."
            )
        }), 401

    if not user_msg:
        user_msg = f"Generate an immediate emergency action and preparedness plan for a {role} based on the latest cyclone telemetry."

    system_prompt = _build_system_prompt(role, context)

    # Prepare message list for Groq
    messages = [{"role": "system", "content": system_prompt}]

    # Append recent conversation history (up to last 6 turns)
    for turn in history[-6:]:
        if isinstance(turn, dict) and "role" in turn and "content" in turn:
            if turn["role"] in ("user", "assistant"):
                messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": user_msg})

    # Call Groq API directly via requests
    try:
        import requests
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # Try specified model first, then fallback to other active models if needed
        candidate_models = [model_name]
        for fallback in [DEFAULT_MODEL, "openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-3.3-70b-versatile"]:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        ai_response = None
        used_model = None
        last_error = ""

        for m in candidate_models:
            payload = {
                "model": m,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 1024
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=25)
            if resp.status_code == 200:
                res_data = resp.json()
                ai_response = res_data["choices"][0]["message"]["content"]
                used_model = res_data.get("model", m)
                break
            else:
                last_error = resp.text
                logger.warning(f"Groq model {m} failed ({resp.status_code}): {resp.text}")

        if ai_response is None:
            return jsonify({
                "error": f"Groq API error: {last_error}"
            }), 502

    except Exception as e_http:
        logger.exception("Groq API request failed")
        return jsonify({
            "error": f"Failed to communicate with Groq API: {str(e_http)}"
        }), 500

    return jsonify({
        "response": ai_response,
        "model": used_model,
        "role": role,
        "status": "success"
    }), 200


@ai_bp.post("/scan-room")
@rate_limit(max_per_minute=20)
def scan_room():
    """
    Evaluate room safety during a tropical cyclone based on detected objects,
    cyclone category, and room layout.
    """
    body = request.get_json(silent=True) or {}
    hazards = body.get("hazards", [])
    shelters = body.get("shelters", [])
    room_type = body.get("room_type", "General Room")
    cyclone_category = body.get("category", "VSCS")
    wind_speed = body.get("wind_speed", "120-150 km/h")

    # Rule-based safety score or frontend real-time calculated score
    score = body.get("room_safety_score")
    if score is None:
        score = 70
        if hazards:
            score -= len(hazards) * 15
        if shelters:
            score += len(shelters) * 10
        score = max(15, min(95, score))
    else:
        score = max(10, min(98, int(score)))

    # Determine safety tier
    if score >= 75:
        safety_status = "SAFE_INDOOR_SHELTER"
        status_label = "Optimal Shelter Room"
    elif score >= 50:
        safety_status = "MODERATE_RISK"
        status_label = "Moderate Risk — Mitigation Required"
    else:
        safety_status = "CRITICAL_HAZARD"
        status_label = "High Hazard Room — Relocate Immediately"

    api_key = _get_api_key()

    # If Groq API key is available, generate dynamic expert advice
    ai_guidance = None
    if api_key:
        prompt = (
            f"You are the National Disaster Management Authority (NDMA) Chief Tactical Safety Advisor. "
            f"A severe cyclone (Intensity: {cyclone_category}, Winds: {wind_speed}) is currently impacting the area. "
            f"The user has just performed an indoor camera scan of their {room_type}.\n\n"
            f"DETECTION REPORT:\n"
            f"- Identified Hazards: {', '.join(hazards) if hazards else 'None detected directly'}\n"
            f"- Identified Safe Elements: {', '.join(shelters) if shelters else 'No sturdy shelter furniture detected'}\n"
            f"- Computed Room Safety Score: {score}/100 ({status_label})\n\n"
            f"Provide an immediate, authoritative 4-point tactical instruction:\n"
            f"1. EXACT POSITION TO TAKE: Where exactly should the occupants crouch or shelter right now in this room?\n"
            f"2. GLASS & DEBRIS MITIGATION: Specific steps to neutralize the detected hazards ({', '.join(hazards) if hazards else 'windows'}).\n"
            f"3. HEAD & BODY PROTECTION: Items in the room to grab right now (mattress, pillows, helmet, thick blankets).\n"
            f"4. RELOCATION THRESHOLD: Under what exact structural conditions must they abandon this room for an interior corridor or designated shelter?\n"
            f"Keep the instructions concise, bulleted, bolded, and urgent."
        )

        try:
            import requests
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": DEFAULT_MODEL,
                "messages": [
                    {"role": "system", "content": "You provide urgent, life-saving indoor cyclone shelter directives grounded in NDMA protocols."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
                "max_tokens": 750
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            if resp.status_code == 200:
                ai_guidance = resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"Room scan Groq guidance failed: {e}")

    # Fallback to deterministic expert protocol if AI call didn't execute
    if not ai_guidance:
        hazard_text = f"Identified {len(hazards)} primary hazard zones ({', '.join(hazards)})." if hazards else "No direct glass panes in view."
        shelter_text = f"Identified {len(shelters)} reinforced shelter anchors ({', '.join(shelters)})." if shelters else "No heavy structural tables detected."

        ai_guidance = (
            f"### Official NDMA Indoor Shelter Directive for {cyclone_category} Cyclone\n\n"
            f"**1. Immediate Shelter Position:**\n"
            f"* Move to the lowest floor, interior-most portion of the room away from all exterior facing walls.\n"
            f"* If a sturdy table/desk is detected ({', '.join(shelters) if shelters else 'interior corner'}), crouch underneath it and firmly grasp its legs.\n\n"
            f"**2. Glass & Shard Hazard Mitigation:**\n"
            f"* {hazard_text}\n"
            f"* Immediately draw all heavy curtains and blinds to contain glass fragmentation if windows implode under gale-force winds.\n"
            f"* Reinforce glass with heavy tape in an 'X' pattern or wedge a mattress against the window frame.\n\n"
            f"**3. Personal Protection:**\n"
            f"* Cover your head and torso with thick blankets, quilts, or a mattress to protect against falling roof plaster and flying projectiles.\n"
            f"* Keep emergency go-bag (water, torch, powerbank, medicines) within arm's reach.\n\n"
            f"**4. Evacuation Threshold:**\n"
            f"* If roof rumbling, window frame bowing, or structural wall cracking begins, immediately evacuate into an interior windowless hallway, stairwell, or bathroom."
        )

    return jsonify({
        "status": "success",
        "room_safety_score": score,
        "safety_tier": safety_status,
        "status_label": status_label,
        "hazards_detected": hazards,
        "shelters_detected": shelters,
        "guidance": ai_guidance
    }), 200

