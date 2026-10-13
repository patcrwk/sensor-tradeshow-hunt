PROFILE = {
    "id": "hunt",
    "name": "Hunt run",
    "description": "A scavenger hunt participant's walk: route, steps, stops, steadiness.",
    "replay_model": "sensor",
    "tabs": ["motion", "replay", "story", "timeseries", "environment", "shock", "frequency", "overview"],
    "featured_roles": ["accel", "gyro", "env", "light", "gps"],
    "frequency_role": "accel",
    "story_rules": [
        "duration",
        "peak_event",
        {"rule": "climb", "params": {"min_m": 2.5}},
        "temperature",
        "light",
        "gps_distance",
        "track_distance",
    ],
}
