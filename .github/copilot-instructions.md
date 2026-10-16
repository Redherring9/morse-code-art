# Morse code art

Build a reproducible Python CLI for depth-stacked pulsar-inspired artwork whose
visible strokes encode a configurable Morse message. Preserve 1:3:7 Morse timing
along waveform arc length, wrap between words, and justify rows by uniformly
scaling their Morse unit. Foreground waveforms intentionally occlude background
symbols. Real, attributed pulse profiles are artistic inputs, not a claim that
the output depicts an observed pulse sequence.

## Checkpoints and GitHub synchronization

- Make checkpoint commits at meaningful, working milestones.
- Run appropriate checks before each implementation checkpoint.
- Push each checkpoint to GitHub and verify the remote branch matches the local
  commit.
- Before finishing, commit and push all intended project changes.
- Never commit credentials, virtual environments, caches, or temporary files.
- Never force-push, rewrite history, or overwrite unrelated changes.
- Report authentication or push failures explicitly; do not claim syncing
  succeeded.
- Include directly related documentation and tests with implementation changes.
- Preserve dataset-specific licenses and provenance separately from code.

## Validation

Use the project virtual environment. Install `requirements-dev.txt` for development.
Run `ruff check .`, `ruff format --check .`, and
`python -m unittest discover -s tests -v` before implementation checkpoints.
When changing rendering, also generate and inspect an example; verify PNG
dimensions/DPI and that SVG contains vector paths rather than raster images.
Keep normal generated outputs in the ignored `output/` folder. The intentionally
tracked default example is in `examples/`.
