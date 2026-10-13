from .try_on import CapabilityUnavailable


def capabilities():
    return {
        "status": "experimental",
        "viewer": "model-viewer",
        "asset": "/models/flairify-form.glb",
        "asset_license": "CC0-1.0; original procedural mannequin by the Flairify project",
        "personalized": False,
        "reconstruction": "Not integrated: model quality, capture requirements and garment fitting remain unvalidated.",
        "ar": "Device-dependent; normal 3D viewing remains available.",
    }


def generate(*_):
    raise CapabilityUnavailable(
        "Personalized 3D avatars are unavailable right now."
    )
