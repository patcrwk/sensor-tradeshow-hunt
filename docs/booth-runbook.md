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

1. **Before the show:** Admin > **Printable QR codes**. Enter how many stations
   you plan to have (optionally name them) and click **Generate codes**, then
   **Open printable signs**: one page per station plus a START/FINISH sign.
   Do this on the live site, not on localhost (the page warns you).
   Codes never change once made: raising the count adds signs, lowering it only
   hides the extras, so printed signs stay valid.
   The signs match the show branding (the Waypoint bullseye laminate sheets):
   Home Base and Waypoint 1 to N, each with its QR code in the bullseye.
   **Download print-ready PDF** gives US Letter, 300 dpi, full-bleed pages for
   a print shop. **Download QR codes and signs (.zip)** adds the signs as PNG,
   the bullseye with the QR on a transparent background (for custom layouts),
   the plain QR codes, and `codes.csv` mapping each file to its sign and link.
   Booth number, website, footer and the "Home Base" / "Waypoint" wording are
   set in Admin > Event and branding. Test-scan every printed sign.
2. Place Station 1 to N and walk the survey **in numbered order**. The mapped
   course takes the printed codes (and names) automatically.
3. Course Setup > your course > Rules and identity: tick **QR code scans**
   (or use the button in Admin). With GPS also ticked, both must agree.
   Signs only check in while their course is the active one. Course Setup >
   **Print QR signs** reprints a single course's signs if needed.
4. At check-out, a **phone QR** appears for the participant. They scan it once:
   it opens their personal hunt page and links their phone to their run.
   ("Phone QR" in the Out on the course list shows it again.)
5. At each station: scan the sign, then rest the sensor for 10 seconds.
6. Scans are matched to the sensor's rests automatically, even if the sensor
   clock is a few minutes off. The run page lists every scan and whether it
   paired with a rest. A scan with no rest near it does not count.
7. When the run is published, the participant's own page shows their time,
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
