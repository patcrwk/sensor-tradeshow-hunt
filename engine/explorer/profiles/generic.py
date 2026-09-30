PROFILE = {
    "id": "generic",
    "name": "Generic",
    "description": "Any enDAQ recording.",
    "tabs": ["overview", "timeseries", "frequency", "shock", "environment", "motion", "story"],
    "featured_roles": ["accel", "gyro", "env", "light", "gps"],
    "frequency_role": None,          # None = high-rate accel when present
    "story_rules": [
        "duration",
        "peak_event",
        {"rule": "dominant_frequency", "params": {"band": [5, 1000], "label": "Dominant vibration"}},
        {"rule": "climb", "params": {"min_m": 3.0}},
        "temperature",
        "light",
        "gps_distance",
    ],
}
