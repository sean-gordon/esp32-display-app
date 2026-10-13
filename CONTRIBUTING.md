# Development and publication

The repository is private. `main` is the release baseline; `development` is the
working branch for updates. Branch protections are not configured automatically.

Before committing:

```sh
git switch development
git add .
python scripts/check_secrets.py
python -m unittest discover -s tests -v
git commit -m "Describe the change"
git push origin development
```

Keep real ESPHome credentials in your Home Assistant secrets.yaml. Never add
secrets.yaml, .env files, downloaded firmware, app data, or device addresses.
The example secrets file must retain placeholder values. Review `git diff --cached`
before committing. The scanner examines Git's staged contents and reports file
names/categories without printing sensitive values. Its heuristic checks are not
an exhaustive security guarantee.

First publication is prepared in PUBLISH.ps1. Run it from this repository on a
computer with working GitHub access after `gh auth login`. It creates a NEW private
repository, pushes main and development, and keeps main as the default branch.
Do not run it from an extracted source archive without Git history.

A private GitHub repository is not offered as an unauthenticated Home Assistant
App store repository. Install by copying the app folder into local_apps. For an
update, copy the revised esp32_display folder, increment its config.yaml version,
then use Check for updates and Update in Home Assistant. Firmware changes require
ESPHome Validate/Install separately. This project does not deploy from GitHub to
Home Assistant automatically.
