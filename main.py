import yaml
import random
import openai
from pathlib import Path
from datetime import datetime

# === Load Config ===
with open("config.yaml", "r") as f:
    CONFIG = yaml.safe_load(f)

# === Global Variables ===
HISTORY_FILE = Path("history.md")
STATE = {
    "population": CONFIG["initial_population"],
    "activities": {},
    "resources": CONFIG["initial_resources"],
    "history": []
}

# === Production Rules ===
PRODUCTION_RULES = CONFIG["production_rules"]

# === Helper Classes ===
class Activity:
    def __init__(self, name, workers):
        self.name = name
        self.workers = workers
    
    def produce(self):
        rules = PRODUCTION_RULES.get(self.name, {})
        total = 0
        for w_type, count in self.workers.items():
            eff = rules.get("workers", {}).get(w_type, 0)
            total += count * eff
        return total

class NonStockableActivity(Activity):
    def produce(self, need):
        produced = super().produce()
        return min(100, (produced / need) * 100 if need > 0 else 100)

# === Compact Rendering ===
def render_compact(state):
    lines = []
    pop = state["population"]
    res = state["resources"]
    line1 = f"👥{pop['total']} (💪{pop['workers']})"
    line2 = f"🧔‍♂️{pop['men']} 👩{pop['women']} 🤰{pop['pregnant']} 👶{pop['babies']} 🧒{pop['children']} 👴{pop['elders_m']} 👵{pop['elders_f']}"
    line3 = f"🥫{res['food']['stock']} (+{res['food']['prod']}) | ~{res['food']['turns']}t/{res['food']['capacity']}"
    lines.extend([line1, line2, line3])
    return "\n".join(lines)

# === Events ===
def trigger_events():
    events = CONFIG["events"]
    triggered = []
    for event in events:
        if random.random() < event["probability"]:
            triggered.append(event)
    return triggered

# === History Logging ===
def log_history(entry):
    STATE["history"].append(entry)
    with open(HISTORY_FILE, "a") as f:
        f.write(f"\n### {datetime.now().strftime('%Y-%m-%d %H:%M')}\n{entry}\n")

# === LLM Adviser ===
def ask_adviser(state, events):
    client = openai.OpenAI(api_key=CONFIG["openai_api_key"])
    prompt = CONFIG["prompts"]["master"].format(
        state=render_compact(state),
        events="\n".join([e["description"] for e in events])
    )
    resp = client.chat.completions.create(
        model=CONFIG["openai_model"],
        messages=[{"role": "system", "content": "You are the game master."},
                  {"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content

# === Game Loop Example ===
def run_turn():
    events = trigger_events()
    advice = ask_adviser(STATE, events)
    print("=== STATE ===")
    print(render_compact(STATE))
    print("=== EVENTS ===")
    for e in events:
        print("-", e["description"])
    print("=== ADVISER ===")
    print(advice)
    log_history(advice)

if __name__ == "__main__":
    run_turn()
