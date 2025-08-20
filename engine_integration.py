# engine_integration.py
from pathlib import Path
from datetime import datetime
from typing import List, Dict

from engine import Tribe, Assignments, Demographics, Resources
from engine import render_compact, build_advisor_prompt as build_prompt_core  # si tu gardes ta version
from engine import InertiaTracker, EventEngine, EventSpec

HISTORY_PATH = Path("history.md")

class HistoryBuffer:
    def __init__(self, max_lines: int = 30):
        self.max_lines = max_lines
        self.lines: List[str] = []

    def add(self, text: str):
        for line in text.strip().splitlines():
            self.lines.append(line)
        if len(self.lines) > self.max_lines:
            self.lines = self.lines[-self.max_lines:]

    def recent_text(self) -> str:
        return "\n".join(self.lines)

def append_history_file(compact_block: str, advisor_text: str, events: List[str], last_actions: str):
    ts = datetime.utcnow().isoformat(timespec="seconds")
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(f"## Tour @ {ts} UTC\n")
        f.write(compact_block + "\n\n")
        f.write("**Conseiller**\n\n" + advisor_text.strip() + "\n\n")
        f.write("**Événements**\n\n" + ("\n".join(events) if events else "(aucun)") + "\n\n")
        f.write("**Actions**\n\n" + (last_actions or "(N/A)") + "\n\n---\n")

def build_advisor_prompt(report_json: Dict, compact_block: str, history_text: str, events: List[str], last_actions: str) -> str:
    """
    Cette fonction charge build_advisor_prompt.md et injecte:
    - le rendu compact
    - un JSON d'état exploitable
    - l'historique récent
    - les événements
    - les dernières actions du joueur
    """
    base = Path("build_advisor_prompt.md").read_text(encoding="utf-8")
    state_json_str = json_dumps_safe(report_json)

    dynamic = f"""
# CONTEXTE ACTUEL

[COMPACT]
{compact_block}

[STATE_JSON]
{state_json_str}

[HISTORIQUE_RÉCENT]
{history_text}

[ÉVÉNEMENTS]
{chr(10).join(events) if events else "(aucun)"}

[DERNIÈRES_ACTIONS_DU_JOUEUR]
{last_actions}
"""
    return base + "\n" + dynamic

def json_dumps_safe(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2)

def openai_advisor(prompt: str) -> str:
    # Branche ton client ici si tu veux une vraie réponse
    # Fallback local pour éviter une dépendance à l’instant T
    return "Conseiller: Les stocks tiennent, mais la pêche peut surprendre. Option prudente: renforcer 🥫. Option audacieuse: basculer 2 adultes vers 🐟. Option créative: rituel court pour la cohésion."

def run_one_turn(tribe: Tribe, inertia: InertiaTracker, event_engine: EventEngine,
                 history_buf: HistoryBuffer, last_actions: str, turn: int):
    # 1) Moteur calcule l'état
    report = tribe.next_turn()

    # 2) Inertie post-calcule sur les flux stockables
    adjusted = inertia.apply(tribe.assign.per_activity, report["flows"])
    report["flows"] = adjusted  # on remplace par les flux après inertie

    # 3) Événements paramétrés
    events = event_engine.roll(tribe)

    # 4) Rendu compact
    compact_block = render_compact(report, tribe.assign, tribe.demo)

    # 5) Construire le prompt conseiller à partir du .md et du contexte dynamique
    prompt = build_advisor_prompt(
        report_json=report,
        compact_block=compact_block,
        history_text=history_buf.recent_text(),
        events=events,
        last_actions=last_actions
    )

    # 6) Appel LLM conseiller
    advisor_text = openai_advisor(prompt)

    # 7) Afficher en console
    print("\n===== TOUR", turn, "=====")
    print(compact_block)
    print("\nConseiller >\n", advisor_text)
    print("\nÉvénements >")
    for e in events:
        print(" -", e)

    # 8) Historiser
    append_history_file(compact_block, advisor_text, events, last_actions)
    history_buf.add(f"[Tour {turn}] {advisor_text}")

    # 9) Retour si besoin
    return {
        "report": report,
        "compact": compact_block,
        "events": events,
        "advisor": advisor_text,
        "prompt_used": prompt
    }
