from backend.app.services.vision_client import _parse_json_object


def test_parse_json_object_from_wrapped_model_output() -> None:
    payload = _parse_json_object(
        'Here is JSON: {"visible_observations":["white smoke"],"visible_text":[],"visible_components":["exhaust"],"uncertainties":[]}'
    )
    assert payload["visible_observations"] == ["white smoke"]

