# Calibration evidence and limits

The app must accommodate the board's chosen geometry rather than assume one universal
SMD or through-hole clearance rule. Burn width depends on coating, focus, process,
direction and cleanup. Etching may alter the final width again.

## Recorded development observations

- A provisional elliptical paint-removal model used X/Y widths of **0.22/0.33 mm**.
  This is trial process evidence, not an intrinsic optical specification.
- A 45 × 30 mm coupon took **125 seconds** through the earlier print workflow.
- A later four-pattern direct-print power comparison took **62 seconds** at speed 10,
  600 DPI and 2500 Hz, with powers 6–9%. Cleaned stroke widths looked broadly similar;
  this did not establish identical widths or a universally optimal power.
- A real board isolation run took **19 minutes 3 seconds** through its then-current
  workflow. Its file ordering and settings must not be mixed with later encoder changes.
- A post-etch photo suggested roughly **0.30–0.40 mm** clearance around a 0.35 mm
  target. That was an image estimate (about ±0.05 mm), not enough to derive a precise
  etch allowance. Approximate drilled-hole alignment estimates were likewise not
  metrology or proof of sub-0.10 mm registration.

Current direct timing is a provisional model anchored to the 62-second coupon and
reported with uncertainty. Route optimization changes beam-off travel; a reduction
in travel distance is not the same percentage reduction in total engraving time.
One Arduino Micro software test reduced calculated travel from about 11.6 m to 0.5 m
while preserving all engraving segments and intentional repeated exposures.

At 600 DPI, coordinate-grid spacing is 0.042333 mm; at 1200 it is 0.021167 mm.
Grid rounding and repeated exposures remain visible/recorded. Compensation, coverage
and thermal behavior are approximate. Fallback into an undersized gap deliberately
sacrifices copper and must be inspected; tapered dead ends into solid copper are
rejected so they do not create unnecessary diagonal thermal-spoke burns.

The original photos, full measurements and comparison artifacts are retained locally,
not shipped with the source repository. Process presets and stronger post-etch
calibration are future work; current values should not be copied blindly to hardware.
