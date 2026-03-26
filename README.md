# Memoria

A memory contradiction puzzle box.

A simulated user named Alex has been observed for 12 months. The system collected ~270 structured conclusions about them — but the conclusions contradict each other. People change, lie to themselves, behave differently in different contexts, and sometimes the inference system gets it wrong.

Your job: figure out what's true.

---

## Get Started

```bash
git clone https://github.com/thrialectics/memoria.git
cd memoria/starter-kit
pip install httpx
python tutorial.py
```

The tutorial connects to the hosted API and walks you through everything.

---

## API

The puzzle API is live at **https://memoria-puzzle.up.railway.app**

| Endpoint | Description |
|----------|-------------|
| `POST /sessions` | Start a new session |
| `GET /sessions/{id}/conclusions` | All ~270 conclusions about the user |
| `GET /sessions/{id}/questions` | Questions your answers are scored against |
| `POST /sessions/{id}/submit` | Submit a reconciliation policy |
| `POST /sessions/{id}/answers` | Submit answers directly (write your own logic) |
| `GET /rules` | Policy schema and scoring rules |
| `GET /attributes` | Attribute definitions and valid values |
| `GET /docs` | Interactive API documentation |

---

## Files

```
starter-kit/
├── tutorial.py       # Start here — guided interactive walkthrough
├── custom_solver.py  # Write your own reconciliation logic (unlocked during tutorial)
└── solver.py         # Client library + analysis helpers
```
