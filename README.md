# Tribal Game Simulator

A turn-based simulation game where you manage a prehistoric tribe.  
The system computes production, consumption, demographics, and applies random events.  
An LLM (via OpenAI API) acts as your **counselor**, providing narrative flavor and strategic hints.  

---

## Features
- **Population management**: adults, children, elders, specialists, leaders.
- **Production system**: agriculture, hunting, fishing, crafting, storage, etc.
- **Non-stockable activities**: childcare, culture, education, organization.
- **Events engine**: configurable random events with probability, gravity, and cooldowns.
- **Compact reporting**: a concise tribal dashboard per turn.
- **YAML configuration**: tweak production weights, events, and probabilities without editing code.
- **History tracking**: all turns logged in `history.md`.

---

## Example of compact report
```
👥94 (💪31)
🥫1250(+260)•🧔‍♂️3 | \~13t/24
🍛+360(-100)=+260 net
🔧70(+30)•🧔‍♂️3
🎭85%•🧑‍🎨1🧔‍♂️2
👩‍🍼100%•👩3👵1
```

---

## Installation
See [install.md](install.md).

## Configuration
Edit [`config.yaml`](config.yaml) to change:
- production rules
- event probabilities
- cooldown inertia for each activity

---

## Running
```bash
python main.py
```

This will:

1. Compute tribe stats for the turn.
2. Apply random or scheduled events.
3. Ask the LLM counselor for narrative output.
4. Append everything to `history.md`.
5. Print the compact tribal dashboard in console.