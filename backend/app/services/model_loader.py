"""
CycloSense — Model Loader Service
Loads all three trained models and the scaler once at application startup.
Models are stored as module-level singletons so they are shared across requests.
"""

import os
import gc
import pickle
import logging
import threading

import torch
import torchvision.models as tv_models
from ultralytics import YOLO

# Limit PyTorch to 1 thread to avoid memory spikes and CPU thrashing on 512MB RAM cloud hosts
torch.set_num_threads(1)

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
_BASE = os.path.join(os.path.dirname(__file__), "..", "..", "weights")

WEIGHTS = {
    "model1": os.path.join(_BASE, "model1_detection.pt"),
    "model2": os.path.join(_BASE, "model2_classification.pt"),
    "model3": os.path.join(_BASE, "model3_forecasting.pt"),
    "scaler":  os.path.join(_BASE, "model3_scaler.pkl"),
}

# ── IMD intensity classes (3-class: D+DD→D_DD, SCS+SuCS→VSCS) ──────────────────────
CLASSES = ["CS", "D_DD", "VSCS"]   # sorted alphabetically — must match training
NUM_CLASSES = len(CLASSES)

# ── LSTM hyper-parameters (must match training config) ───────────────────────
LSTM_INPUT_SIZE  = 3    # (lat, lon, wind_speed)
LSTM_HIDDEN_SIZE = 64
LSTM_NUM_LAYERS  = 2
LSTM_OUTPUT_SIZE = 3    # predict (lat, lon, wind_speed)
LSTM_SEQ_LEN     = 8   # 8 × 3-hour steps = 24 hours of history

# ── Singleton holders & Individual Locks ─────────────────────────────────────
_model1 = None   # YOLOv8-nano  (ultralytics.YOLO)
_model2 = None   # EfficientNet-B0, 3-class (torch.nn.Module, eval mode)
_model3 = None   # 2-layer LSTM    (torch.nn.Module, eval mode)
_scaler = None   # sklearn StandardScaler

_lock1 = threading.Lock()
_lock2 = threading.Lock()
_lock3 = threading.Lock()


# ──────────────────────────────────────────────────────────────────────────────
# Internal LSTM definition — must match the architecture used during training
# ──────────────────────────────────────────────────────────────────────────────
class CycloneLSTM(torch.nn.Module):
    """2-layer LSTM that predicts next (lat, lon, wind_speed) from a sequence."""

    def __init__(self, input_size=3, hidden_size=64, num_layers=2, output_size=3):
        super().__init__()
        self.lstm = torch.nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=0.2,
        )
        self.fc = torch.nn.Linear(hidden_size, output_size)

    def forward(self, x):
        out, _ = self.lstm(x)          # (batch, seq, hidden)
        return self.fc(out[:, -1, :])  # take last time-step → (batch, output)


# ──────────────────────────────────────────────────────────────────────────────
# Lazy, Memory-Efficient Loaders
# ──────────────────────────────────────────────────────────────────────────────

def get_model1() -> YOLO:
    """Load and return YOLOv8 detection model on demand."""
    global _model1
    if _model1 is None:
        with _lock1:
            if _model1 is None:
                path = WEIGHTS["model1"]
                logger.info("Loading Model 1 (YOLO detection) on-demand from %s", path)
                _model1 = YOLO(path)
                gc.collect()
                logger.info("Model 1 ready in memory.")
    return _model1


def get_model2() -> torch.nn.Module:
    """Load and return EfficientNet-B0 classification model on demand."""
    global _model2
    if _model2 is None:
        with _lock2:
            if _model2 is None:
                path = WEIGHTS["model2"]
                logger.info("Loading Model 2 (EfficientNet) on-demand from %s", path)
                device = torch.device("cpu")
                model = tv_models.efficientnet_b0(weights=None)
                in_features = model.classifier[1].in_features
                model.classifier = torch.nn.Sequential(
                    torch.nn.Dropout(p=0.4, inplace=True),
                    torch.nn.Linear(in_features, NUM_CLASSES),
                )
                state = torch.load(path, map_location=device, weights_only=False)
                if isinstance(state, dict) and "model_state_dict" in state:
                    state = state["model_state_dict"]
                model.load_state_dict(state)
                model.to(device)
                model.eval()
                _model2 = model
                gc.collect()
                logger.info("Model 2 ready in memory.")
    return _model2


def get_model3():
    """Load and return (lstm_model, scaler) tuple on demand."""
    global _model3, _scaler
    if _model3 is None or _scaler is None:
        with _lock3:
            if _model3 is None or _scaler is None:
                m3_path = WEIGHTS["model3"]
                sc_path = WEIGHTS["scaler"]
                logger.info("Loading Model 3 (LSTM) on-demand from %s", m3_path)
                device = torch.device("cpu")
                model = CycloneLSTM(
                    input_size=LSTM_INPUT_SIZE,
                    hidden_size=LSTM_HIDDEN_SIZE,
                    num_layers=LSTM_NUM_LAYERS,
                    output_size=LSTM_OUTPUT_SIZE,
                )
                state = torch.load(m3_path, map_location=device, weights_only=False)
                if isinstance(state, dict) and "model_state_dict" in state:
                    state = state["model_state_dict"]
                model.load_state_dict(state)
                model.to(device)
                model.eval()

                logger.info("Loading scaler from %s", sc_path)
                with open(sc_path, "rb") as f:
                    scaler = pickle.load(f)

                _model3 = model
                _scaler = scaler
                gc.collect()
                logger.info("Model 3 and scaler ready in memory.")
    return _model3, _scaler


def get_models_status() -> dict:
    """Check readiness of each individual model."""
    return {
        "model1_yolo": _model1 is not None,
        "model2_classification": _model2 is not None,
        "model3_forecasting": _model3 is not None,
        "scaler": _scaler is not None,
        "any_loaded": any([_model1 is not None, _model2 is not None, _model3 is not None]),
        "all_loaded": all([_model1 is not None, _model2 is not None, _model3 is not None, _scaler is not None]),
    }


def are_models_loaded() -> bool:
    """Return True if all models are loaded."""
    return get_models_status()["all_loaded"]


def load_all_models():
    """Load all models (for diagnostics)."""
    get_model1()
    get_model2()
    get_model3()
    logger.info("All models loaded.")
