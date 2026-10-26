# Booth staff runbook

## 1. Setup (day before or morning of)

1. Start the laptop, then run `make show` in the project folder. Wait for both
   services (engine on port 8000, web on 3000).
2. Open http://localhost:3000/display on the big monitor (`make kiosk` on macOS).
   It needs no mouse and updates by itself.
3. Admin: set the event name, logo and colors; choose the kiosk panels.
   To show YouTube videos, paste each link under Kiosk rotation > YouTube
   videos, click Add, then Save rotation. Each time the rotation reaches the
   video panel it plays the next video, to the end by default. Videos are
   muted unless "Sound on" is ticked and the display was opened with
   `make kiosk` (browsers block autoplay with sound otherwise). The display
   needs internet access for YouTube; a video that cannot play is skipped.
   The **Recording Explorer walkthrough** panel plays one recording's 3D
   replay (the whole recording in about 45 s), then its story, shock,
   spectrum, environment and route screens. Pick the recording under Kiosk
   rotation (default: the first Demo Library recording).
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
10. To tidy up, **Archive** old or test courses: they move to "Old courses"
    at the bottom of the list and can be restored. Recordings work the same
    way (Archive in Recent uploads or on the recording page; "Old
    recordings" holds them). Rename a recording on its page. Or **Delete** (Course Setup list, or on the
    course page). The active course cannot be deleted: make another one active
    first. Runs scored against a deleted course keep their times and results.
    Printed QR signs are not affected.

### Lessons from the first real test (Oct 12)

- The S3-D40 and S4-E100D40 sensors record **no GPS**. Maps are reconstructed
  from steps and heading, and the course is identified by QR scans (the default
  for a course without GPS).
- **Turn on the rotation (gyro) channel** in the sensor configuration. Without it
  the route cannot be reconstructed at all.
- **Do not scan QR codes during the survey walk.** Just rest the sensor 15 to 20
  seconds at Home Base, each Waypoint in numbered order, and Home Base again.
- A reconstructed map has no compass direction. In Course Setup > Map and
  stations, use **Turn** and **Flip** to line it up with the hall, or upload a
  **static map** (Admin) and switch it on.
- At check-out, the participant **must scan their personal QR first**, on the
  phone they will use for the station signs. Runs with no scans are flagged for
  review.
- Sensor serials can be typed as printed on the label (S0014201); they match the
  file's 14201.
- Recommended survey (Oct 13): walk it with the **S4D40**, then in Course Setup
  turn/flip the map to match the hall and drag any waypoint that sits in the
  wrong place. Participant routes are fitted to the waypoints, so they line up
  with whatever you set. Both sensor models work for participants.

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
3. Course Setup > your course > Rules and identity: check **QR code scans** is
   ticked (it is the default when the course has no GPS). With another method
   also ticked, both must agree, so untick any you are not using.
   Signs only check in while their course is the active one. Course Setup >
   **Print QR signs** reprints a single course's signs if needed.
4. At check-out, a **phone QR** appears for the participant. They scan it once:
   it opens their personal hunt page and links their phone to their run.
   ("Phone QR" in the Out on the course list shows it again.)
5. At each station: scan the sign, then rest the sensor for 10 seconds.
   Participants can scan with the **Scan next sign** button on their hunt page
   (opens the camera inside the page, so they never leave it) or with the phone
   camera app. The first time, the phone asks to allow the camera. If a phone
   reopens an old tab of the same sign (common with Home Base, scanned at the
   start and finish), the page records the scan again when it comes back.
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
