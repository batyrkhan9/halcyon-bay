# Halcyon Bay

Cal Hacks 13.0 project. An autonomous system of work that runs the patient billing office of a fictional California nonprofit hospital, Halcyon Bay Community Hospital. It works every self-pay account, screens patients for financial assistance under federal 501(r) and California law, learns the hospital's policies from 18 months of history, turns staff corrections into new rules, and logs every step.

Full context, ownership, contracts and timeline: @PRD.md

## Who owns what

Three people build this at the same time.

- `core/` is the system of work and the agent (Batyrkhan)
- `data/` is the simulated hospital world and the answer key (teammate 2)
- `ui/` is the screens (teammate 2)
- `docs/` is the pitch, slides, Devpost text and demo script (teammate 3)

Only change files in the folders owned by the person you are working with. If something in another folder needs to change, say so instead of editing it. The data format shared by `core/` and `data/` changes only when both owners agree.

## Rules

- Legal math (poverty level thresholds, deadlines) and permission checks live in plain code, never in a prompt.
- The AI proposes and never approves. Only the gateway posts changes.
- All data is synthetic. Never use a real patient, a real hospital or real personal data.
- API keys live only in `.env`. Never put a key in code or commit it.
- Run `git pull --rebase` before every push.

## Commits

- Never add Claude as a co-author. No Co-Authored-By trailer, no Generated with Claude Code line and no Claude-Session link in commits or pull requests. The three team members are the only authors.
