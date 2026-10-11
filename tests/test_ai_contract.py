import json
from types import SimpleNamespace
import pytest
from app.services import ai


def test_model_boxes_are_validated_and_converted(monkeypatch):
    garment = {
        "name": "Visible jacket",
        "category": "jacket",
        "colour": "white",
        "pattern": "solid",
        "visible_details": "lapels",
        "bbox": [100, 200, 900, 800],
        "uncertainty": [],
    }
    sent = []

    def generate(**kwargs):
        sent.append(kwargs)
        return SimpleNamespace(text=json.dumps({"garments": [garment]}))

    monkeypatch.setattr(
        ai, "client", lambda **k: SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    )
    item = ai.detect(b"validated-image")[0]
    assert item.box.model_dump() == {"x": 0.2, "y": 0.1, "width": 0.6, "height": 0.8}
    assert sent[0]["config"].response_schema is ai.VisionResult
    assert sent[0]["config"].max_output_tokens == 4096
    garment["bbox"] = [100, 900, 900, 200]
    with pytest.raises(ValueError, match="invalid garment location"):
        ai.detect(b"validated-image")
