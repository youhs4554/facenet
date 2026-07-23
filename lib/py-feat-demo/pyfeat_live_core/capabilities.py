from __future__ import annotations


def capabilities_for(detector_type: str) -> dict:
    if detector_type == "Detectorv1":
        return {
            "detector_type": "Detectorv1",
            "landmark_space": "dlib68",
            "overlay_kind": "dlib68",
            "has_valence_arousal": False,
            "has_blendshapes": False,
            "has_gaze": True,
            "models": {
                "face_model": ["retinaface", "img2pose"],
                "facepose_model": ["pose_mlp", "pnp_dlt", "img2pose"],
                "landmark_model": ["mobilefacenet", "mobilenet", "pfld"],
                "au_model": ["xgb", "svm", None],
                "emotion_model": ["resmasknet", "svm", None],
                "identity_model": [None, "arcface", "facenet"],
                "gaze_model": ["l2cs", None],
            },
        }
    return {
        "detector_type": "Detectorv2",
        "landmark_space": "mp478",
        "overlay_kind": "mesh478",
        "has_valence_arousal": True,
        "has_blendshapes": True,
        "has_gaze": True,
        "models": {
            "identity_model": [None, "arcface", "facenet"],
        },
    }


def all_capabilities() -> dict:
    return {
        "Detectorv2": capabilities_for("Detectorv2"),
        "Detectorv1": capabilities_for("Detectorv1"),
    }


def compute_info() -> dict:
    info = {
        "cpu": {"available": True, "label": "CPU"},
        "mps": {"available": False, "label": "Apple Metal"},
        "cuda": {"available": False, "label": "CUDA"},
    }
    try:
        import torch

        info["cuda"]["available"] = bool(torch.cuda.is_available())
        info["mps"]["available"] = bool(
            hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
        )
    except Exception:
        pass
    return info

