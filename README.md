# Halcyon Bay

An autonomous system of work that runs the patient billing office of a nonprofit hospital. Built at Cal Hacks 13.0.

Everything here is simulated: the hospital, the patients and the accounts. No real patient data is used.

## Folders

| Folder | Owner | What goes there |
|---|---|---|
| `core/` | Batyrkhan | The system of work and the agent |
| `data/` | Noriaki | The simulated hospital world, the answer key and the CRS calls |
| `ui/` | Noriaki | The screens |
| `docs/` | Ifeoluwa | Pitch, slides, Devpost text, demo script |

## Run the demo

You need Python 3.12, [uv](https://docs.astral.sh/uv/) and Node.js. No API key is needed.

1. Install the core once:

   ```bash
   uv venv core/.venv --python 3.12
   uv pip install --python core/.venv/bin/python -r core/requirements.txt
   ```

2. Start the demo, then open http://localhost:8000:

   ```bash
   core/.venv/bin/python -m core.demo --day 2026-07-14
   ```

It loads the history, finds the day-one discoveries, replays the live days to the day you pick and serves the screens. The first run also builds the screens. Use `--day 2026-09-30` to show the final score. Only the judge box and new staff corrections call Claude live; they need `ANTHROPIC_API_KEY` in `.env`. To reset between takes, run `python3 data/tools/add_account.py --reset`, then start the demo again.

## Setup for development

1. Clone the repo.
2. Copy `.env.example` to `.env` and add your keys. Never commit `.env`.
3. Run `git pull --rebase` before every push.
