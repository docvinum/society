# Installation Guide

## 1. Prerequisites
- Python 3.9+
- pip (Python package manager)
- An OpenAI API key (required for the counselor system)

## 2. Clone the repository
```bash
git clone https://github.com/yourusername/tribal-game-simulator.git
cd tribal-game-simulator
```

## 3. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate   # Linux & macOS
venv\Scripts\activate      # Windows
```

## 4. Install dependencies

```bash
pip install -r requirements.txt
```

## 5. Configure the game

Edit `config.yaml` to adjust:

* production weights
* event probabilities and cooldowns
* counselor parameters

## 6. Set your OpenAI API key

### Linux & macOS
```bash
export OPENAI_API_KEY="sk-xxxx"   # Linux & macOS
```
### Windows
```bash
setx OPENAI_API_KEY "sk-xxxx"     # Windows
```

## 7. Run the game

```bash
python main.py
```

---

## Notes

* The game writes logs to `history.md`
* You can reset progress by deleting or renaming `history.md`
* The LLM counselor is optional: if no API key is set, the game still runs with mechanical events.