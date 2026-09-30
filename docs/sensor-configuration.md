# Sensor configuration for the event

Apply with enDAQ's configuration software. Survey sensors and participant
sensors use the same configuration.

| Channel | Setting |
|---|---|
| GPS / GNSS | **On**, highest rate the model supports (1 Hz minimum) |
| 40g DC acceleration | 200 Hz or higher (stillness, steps, orientation). 1000 Hz only if vibration beacons are used. |
| IMU rotation (channel 47 or equivalent) | 100 Hz |
| Internal pressure / temperature / humidity | 10 Hz |
| Light | On, default rate |
| 100g PE acceleration, high-rate gyro | **Off** for hunt sensors (Explorer demos may use any configuration) |

- Sync the sensor clock before the show. GPS time, when recorded, is used to
  check it.
- **GPS fix rule:** power sensors on and let them get a fix before handing them
  out. Cold starts can take a minute or more.
- Verify recording sizes with a test walk (a 10 minute walk at the rates above
  should be a few MB).
- Recordings are read from the sensor's `DATA` folder when it mounts as a USB
  drive (configurable in `engine/config.yaml` and Admin).

The engine finds channels by what they measure, so channel numbers may differ
between models. Run `make tune FILE=<file>.IDE` on a test recording and check
the "Channel discovery" section: `accel`, `gyro`, `env`, `light` and a location
channel should all be found.
