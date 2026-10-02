# Booth staff runbook

## 1. Setup (day before or morning of)

1. Start the laptop, then run `make show` in the project folder. Wait for both
   services (engine on port 8000, web on 3000).
2. Open http://localhost:3000/display on the big monitor (`make kiosk` on macOS).
   It needs no mouse and updates by itself.
3. Admin: set the event name, logo and colors; choose the kiosk panels.
4. Admin > Watch folder: set the sensor's mount path, for example
   `/Volumes/*/DATA`. Plugged-in sensors are then read automatically.
5. Sensors: configure them with enDAQ's software (see
   `sensor-configuration.md`). Sync their clocks. Charge them.

## 2. Survey walk (maps the course)

1. Place the station markers at least 15 to 20 m apart (and holders, tap-code
   signs or beacons if the course uses them).
2. Power on the survey sensor. **Wait for a GPS fix** outdoors or near a window.
   A cold start can take a minute or more.
3. Rest the sensor at the booth START marker for **15 seconds**.
4. Walk to each station **in numbered order**. At each one rest the sensor for
   **15 to 20 seconds**.
   - Tap codes: tap the station number, then rest.
   - Holders: rest it in the holder.
5. Return and rest at FINISH for 15 seconds.
6. Optional: walk again in a different order; add the second file to the same
   course to average station positions.
7. Course Setup > New course: upload the file(s). Read the **Venue GPS quality**
   box. If it says POOR, the course runs on dead reckoning and stations must be
   identified by holders or tap codes; tick those identity methods.
8. Review the map. Fix any misplaced station by dragging it. Rename stations,
   mark bonus stations, set the order rule. Read any spacing warnings.
9. Publish. Export the package and keep it with the booth kit: the same venue
   next year can import it.

## 2b. QR check-ins (GPS fallback, needs the hosted app)

Use when GPS is poor in the hall and you do not want holders or tap codes.
Participants scan a printed QR sign at each station with their phone camera;
the sensor's 10 second rest still proves the stop.

1. Course Setup > your course > Rules and identity: tick **QR code scans**.
   (With GPS also ticked, both must agree.)
2. Click **Print QR signs**: one page per station plus a START/FINISH sign for
   the booth. Print once; the codes survive re-mapping and new versions of the
   course. They only work while that course is the active one.
3. At check-out, a **phone QR** appears for the participant. They scan it once:
   it opens their personal hunt page and links their phone to their run.
   ("Phone QR" in the Out on the course list shows it again.)
4. At each station: scan the sign, then rest the sensor for 10 seconds.
5. Scans are matched to the sensor's rests automatically, even if the sensor
   clock is a few minutes off. The run page lists every scan and whether it
   paired with a rest. A scan with no rest near it does not count.
6. When the run is published, the participant's own page shows their time,
   rank, route replay and splits.

## 3. Running the hunt

**Check-out:** Hunt > Check-out. Enter the display name (shown on the big
screen) and the sensor serial. Lead fields appear only if the participant
ticks the consent box. **Make sure the sensor has a GPS fix before handing it
over.**

Tell the participant: "At each station, set the sensor down on the marker and
leave it completely still for 10 seconds. Start and finish the same way at the
booth." Holding it still in a hand does not count; the sensor can tell.

**Return:** plug the sensor in (or drag its `.IDE` file onto Hunt > Returns).
The recording appears with its best match and the reason. Click **Confirm
match**. The run is processed in about a second and appears on the display.
Optionally clear the file from the sensor.

**Needs review:** runs with problems (missing START or FINISH, methods that
disagree) wait in Hunt > Runs > Needs review. Open the run, fix check-ins
(reassign a stray stop, add, remove, or re-time a check-in), write an audit
note, save, then Publish. Detection will sometimes miss; do not stall the line
on it.

**Hide a run** from the display with "Hide from display" on the run page.

## 4. What is scored

- Time runs from the end of the START rest to the start of the FINISH rest.
  Rest time at stations counts.
- Incomplete runs rank below complete ones.
- Peak g is shown per run but never ranked (so nobody drops sensors on purpose).

## 5. End of the event

Admin > Export leads CSV (consented participants only). Then Admin > Reset
event (type RESET): deletes participants, runs, participant recordings and GPS
tracks. Courses and the Demo Library stay.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "No open check-out for sensor" | Check the serial on the check-out, or pick the run manually in the dropdown. |
| Recording started before check-out | The sensor clock is off. Pick the run manually; sync clocks before the next day. |
| START or FINISH not found | The participant did not rest at the booth. Add the check-ins by hand or accept an incomplete run. |
| Many stray stops | GPS radius too small for the hall; raise it in Course Setup > Rules, or add holders. |
| Display not updating | Reload the display page. Check the engine is running (home page shows status). |
