# The fake ABHA directory

**Every person in `mock_directory.json` is invented.** The names, birth years and
UHIDs were made up for the demo; no ABDM call was made to produce them, none of
them corresponds to a real ABHA address, and nothing here was derived from a
real patient record.

`MockABHAProvider` reads this file so that "who is behind this ABHA address" has
an answer in a deployment with no ABDM credentials — which is every deployment
this project has. It is the difference between a demo that can show a returning
patient's history and one that can only show the address being typed in.

Three rules hold this honest, and they are all enforced in code rather than by
this note:

- **`source` stays `"mock"`.** The app keys `isMocked` off that field, not off
  the notice text, and the dashboard says so on screen. A mocked government
  integration is never presented as a live one — `DECISIONS.md §56`.
- **Every demographic block carries `synthetic: true`**, so a consumer that
  reaches past `source` still cannot mistake these for real people.
- **An address not in this file keeps the old behaviour**, including the
  `sha256(address)[0] % 8 == 0` not-found path. Roughly one unknown address in
  eight comes back unverified, so the failure case stays demonstrable instead of
  becoming theoretical the moment fixtures existed.

`asha.devi@sbx` and `ramesh.kumar@sbx` match the two patients `app/services/seed.py`
creates. They are the demo: sign in by phone, see the visits taken in the app;
link the ABHA, see the visit filed under the OPD card as well.
