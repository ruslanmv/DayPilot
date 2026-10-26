# DayPilot Workplace Wellness & Weather

The operator web shell now includes two cross-device hash routes:

- `#/wellness` — an elapsed-time reminder for screen work, a 15-minute break timer, an original illustrated ergonomic station, and animated movement tips.
- `#/weather` — city-search weather from Open-Meteo plus **manually entered** indoor temperature/humidity and actionable comfort prompts.

Both routes appear in desktop navigation and the responsive mobile drawer. The wellness reminder remains mounted while navigating between views; it is not a separate background service.

## Screen-break behavior

- Default timer: 120 minutes; break: 15 minutes. The screen break timer is started by the user and automatically marks a completed 15-minute interval after its countdown ends.
- A persistent in-app reminder appears when the work timer reaches 120 minutes. A browser/OS notification is attempted **only** if the user explicitly grants the Notifications permission. Unsupported/denied permission leaves the in-app reminder intact.
- The monitor and counts are stored only in `localStorage` under `daypilot-workplace-wellness-v1` and survive a brief refresh. An absence longer than one hour starts a fresh session. Pausing and resuming also starts a fresh work interval.
- The timer measures **elapsed time since starting a session**, not actual screen activity, keyboard activity, legal compliance, employee performance, exercise completion, or biometric information. Do not use it for employee surveillance or payroll.
- Screen-work interruptions may also be fulfilled by appropriate tasks that do not require a screen where workplace rules allow. Under the VDT rules illustrated by the provided materials, 15 minutes after 120 minutes is a default; agreements and occupational-health requirements can differ. Do not accumulate pauses at start or end of a shift.
- Animation respects the browser's reduced-motion preference. Stop an exercise if uncomfortable.

## Weather and indoor environment

1. Open Weather; enter the **city** of the workplace. Only the chosen city/location query is sent to Open-Meteo's geocoding API, followed by coordinate-based current-condition forecast data. There is **no automatic browser geolocation request**.
2. Enter real thermometer and hygrometer measurements in the indoor card. DayPilot has no built-in indoor sensor, so those fields are never pre-populated from outdoor weather.
3. Review practical suggestions; ranges are heuristic prompts, **not** a PMV/PPD or ASHRAE/EN/ISO compliance determination. The official [UC Berkeley CBE Thermal Comfort Tool](https://comfort.cbe.berkeley.edu/) uses air temperature, mean radiant temperature, airflow, humidity, clothing and metabolic rate and also supports adaptive models.

At the time of this implementation, Open-Meteo's openly accessible API is suitable for prototyping; review its terms/licensing and usage limits before commercial production deployment. In deployments with strict privacy/CSP policies, the browser must be allowed to reach `https://geocoding-api.open-meteo.com` and `https://api.open-meteo.com`, or weather fetching should be proxied through a consented backend. Weather errors and missing results are shown explicitly, not silently substituted with demo numbers.

## How to test

- `pnpm install --frozen-lockfile`
- `pnpm --filter @daypilot/ui-bridge typecheck`
- `pnpm --filter @daypilot/operator-web build`
- Open `#/wellness` on desktop and on a mobile-width screen; verify the clock, pause/resume/reset, exercise selection, reduced motion, and optional notifications.
- Open `#/weather`; verify that an empty result or disconnected network displays an error; confirm a valid city returns timestamped outdoor values.
- Enter indoor humidity outside 0–100% and temperature outside −10 to 50°C to check validation. Confirm the app **never** labels outdoor weather as indoor readings.

## Future improvements

Optional local sensors (with explicit consent), focus-block integration, shorter microbreak suggestions, and an implementation of validated PMV/PPD calculations can be added later. This initial version deliberately avoids medical or regulatory pass/fail claims.
