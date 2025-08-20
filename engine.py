# engine.py
# Core game engine for the Neolithic proto-RTS
# - Stockable productions and non-stockable coverages
# - Inertia with per-activity cooldowns
# - Parameterized events
# - Compact renderer
# - LLM prompt builder
# - Optional YAML config loader to override seasons, production rules, events

import os
import json
import random
from dataclasses import dataclass, field
from typing import Dict, Tuple, Callable, Optional, List
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # YAML loading is optional; guard load_config accordingly

# Worker emojis
MAN = "🧔‍♂️"; WOMAN = "👩"; PREGNANT="🤰"; BABY="👶"; CHILD="🧒"; GRANDPA="👴"; GRANDMA="👵"; KING="👑"
SPEC_AGRI="🧑‍🌾"; SPEC_FISH="🎣"; SPEC_STORE="🧑‍🍳"; SPEC_TOOLS="🧑‍🏭"; SPEC_SCI="🧑‍🔬"
SPEC_BUILD="👷"; SPEC_ARMY="💂"; SPEC_ART="🧑‍🎨"; SPEC_EDU="🧑🏻‍🏫"; SPEC_ORG="🧑🏻‍💼"; SPEC_NURSE="👩‍⚕️"

def _all_workers():
    return [
        MAN, WOMAN, PREGNANT, BABY, CHILD, GRANDPA, GRANDMA, KING,
        SPEC_AGRI, SPEC_FISH, SPEC_STORE, SPEC_TOOLS, SPEC_SCI,
        SPEC_BUILD, SPEC_ARMY, SPEC_ART, SPEC_EDU, SPEC_ORG, SPEC_NURSE
    ]

def full_rule(**kwargs):
    rule = {w: 0 for w in _all_workers()}
    rule.update(kwargs)
    return rule

# Seasons for agriculture
SEASONAL_AGRI = {"summer": 1.00, "spring": 0.70, "autumn": 0.50, "winter": 0.20}

# Explicit production rules (0 for disallowed workers)
PRODUCTION_RULES: Dict[str, Dict[str, int]] = {
    "🥫": full_rule(**{MAN:100, SPEC_STORE:500}),                            # Storage capacity
    "🌾": full_rule(**{SPEC_AGRI:30, MAN:10, WOMAN:5, CHILD:5}),             # Agriculture (seasonal)
    "🐟": full_rule(**{SPEC_FISH:30, MAN:10, WOMAN:10, CHILD:10}),           # Foraging/Fishing
    "🦌": full_rule(**{SPEC_ARMY:30, MAN:10, WOMAN:5}),                      # Hunting
    "🔧": full_rule(**{SPEC_TOOLS:30, MAN:10, WOMAN:15, CHILD:5}),           # Tools
    "🧪": full_rule(**{SPEC_SCI:30, MAN:10, WOMAN:10, CHILD:1}),             # Science/Engineering
    "🏗": full_rule(**{SPEC_BUILD:30, MAN:20, WOMAN:5}),                      # Construction/Logistics
    "🛡️": full_rule(**{SPEC_ARMY:50, MAN:20, WOMAN:5, CHILD:1}),            # Army capacity
    "🎭": full_rule(), "📚": full_rule(), "👩‍🍼": full_rule(), "🏛": full_rule(),   # Non stockables handled separately
}

# Non stockable rules
NON_STOCK_RULES = {
    "🎭": {"capacity": {SPEC_ART:100, MAN:25, WOMAN:25, GRANDPA:25, GRANDMA:25}, "needs":"population_total"},
    "📚": {"capacity": {SPEC_EDU:10, MAN:5, WOMAN:5, GRANDPA:2, GRANDMA:2}, "needs":"children_only"},
    "👩‍🍼": {"capacity": {SPEC_NURSE:5, WOMAN:2, GRANDPA:1, MAN:1, GRANDMA:1}, "needs":"babies_only"},
}

# Data classes
@dataclass
class Demographics:
    men:int=0
    women_active:int=0
    women_pregnant:int=0
    babies:int=0
    children:int=0
    grandpas:int=0
    grandmas:int=0
    king:int=0
    @property
    def total(self)->int:
        return self.men + self.women_active + self.women_pregnant + self.babies + self.children + self.grandpas + self.grandmas + self.king

@dataclass
class Assignments:
    per_activity: Dict[str, Dict[str,int]] = field(default_factory=dict)
    def count(self, activity:str, worker:str)->int:
        return self.per_activity.get(activity,{}).get(worker,0)

@dataclass
class Resources:
    stocks: Dict[str,int] = field(default_factory=lambda: {"🥫":0, "🔧":0})
    flows: Dict[str,int] = field(default_factory=dict)

@dataclass
class NonStockActivity:
    demo: Demographics
    assign: Assignments
    def _need_value(self, key:str)->int:
        if key=="population_total": return self.demo.total
        if key=="children_only": return self.demo.children
        if key=="babies_only": return self.demo.babies
        return 0
    def coverage(self, activity:str)->Tuple[float,int,float]:
        if activity not in NON_STOCK_RULES: return 0.0,0,0.0
        rule = NON_STOCK_RULES[activity]
        needs = self._need_value(rule["needs"])
        cap = 0.0
        for w, per in rule["capacity"].items():
            cap += per * self.assign.count(activity, w)
        pct = 100.0 if needs==0 else min(100.0, 100.0*cap/float(needs))
        return round(pct,1), needs, cap

# Inertia with cooldowns
@dataclass
class InertiaTracker:
    last_assignments: Dict[str, Dict[str, int]] = field(default_factory=dict)
    penalty: float = 0.10
    threshold: int = 3
    cooldowns: Dict[str, int] = field(default_factory=dict)
    cooldown_len: int = 2
    def apply(self, current_assignments, flows):
        new_flows = dict(flows)
        for act, now in current_assignments.items():
            prev = self.last_assignments.get(act, {})
            moved = 0
            keys = set(now.keys()) | set(prev.keys())
            for k in keys:
                moved += abs(now.get(k,0)-prev.get(k,0))
            if moved > self.threshold:
                self.cooldowns[act] = self.cooldown_len
            if self.cooldowns.get(act,0) > 0 and act in new_flows:
                new_flows[act] = int(new_flows[act] * (1 - self.penalty))
        for act in list(self.cooldowns.keys()):
            self.cooldowns[act] -= 1
            if self.cooldowns[act] <= 0:
                self.cooldowns.pop(act, None)
        self.last_assignments = {a: dict(m) for a,m in current_assignments.items()}
        return new_flows

# Events
@dataclass
class EventSpec:
    name:str
    probability:float
    severity:int
    effect:Callable  # Callable[['Tribe'], str]

@dataclass
class EventEngine:
    specs_by_season: Dict[str, List[EventSpec]] = field(default_factory=dict)
    rng_seed:int = 123
    def __post_init__(self):
        self.rng = random.Random(self.rng_seed)
    def roll(self, tribe:'Tribe')->List[str]:
        season = tribe.season
        out = []
        for spec in self.specs_by_season.get(season, []):
            if self.rng.random() < spec.probability:
                out.append(spec.effect(tribe))
        return out

# Tribe core
@dataclass
class Tribe:
    demo: Demographics
    assign: Assignments
    res: Resources
    season:str="summer"
    king_activity:str="🌾"
    king_bonus:float=0.20

    def population_total(self)->int: return self.demo.total

    def compute_stockable_flows(self)->Dict[str,int]:
        flows: Dict[str,int] = {}
        for activity, rule in PRODUCTION_RULES.items():
            if activity in ("🎭","📚","👩‍🍼","🏛"):
                continue
            base = 0
            for w, coef in rule.items():
                base += coef * self.assign.count(activity, w)
            if activity=="🌾":
                base = int(base * SEASONAL_AGRI.get(self.season,1.0))
            if activity==self.king_activity and self.assign.count(activity, KING)>0:
                base = int(base * (1.0 + self.king_bonus))
            flows[activity] = base
        return flows

    def compute_food_and_storage(self)->Dict[str,int]:
        produced = sum(self.res.flows.get(k,0) for k in ("🌾","🐟","🦌"))
        consumed = self.population_total()  # 1 portion per person per turn
        net = produced - consumed
        cap = 0
        for w, coef in PRODUCTION_RULES["🥫"].items():
            cap += coef * self.assign.count("🥫", w)
        stored = max(0, min(net, cap))
        self.res.flows["🥫"] = stored
        self.res.flows["🍛_net"] = net
        return {"produced":produced,"consumed":consumed,"net":net,"stored":stored,"capacity":cap}

    def update_stocks(self):
        for res_name in ("🥫","🔧"):
            delta = self.res.flows.get(res_name,0)
            if delta:
                self.res.stocks[res_name] = self.res.stocks.get(res_name,0) + delta

    def non_stock_coverages(self)->Dict[str,Dict]:
        nsa = NonStockActivity(self.demo, self.assign)
        out={}
        for act in ("🎭","📚","👩‍🍼"):
            pct, needs, cap = nsa.coverage(act)
            out[act] = {"coverage_pct": pct, "needs":needs, "capacity":cap}
        org_points = self.assign.count("🏛", KING) + 2*self.assign.count("🏛", SPEC_ORG)
        out["🏛"] = {"maturity_index": min(100, 20 + org_points*10) if org_points>0 else 10}
        return out

    def next_turn(self)->Dict:
        self.res.flows = self.compute_stockable_flows()
        food = self.compute_food_and_storage()
        self.update_stocks()
        cover = self.non_stock_coverages()
        return {
            "population_total": self.population_total(),
            "season": self.season,
            "flows": self.res.flows,
            "stocks": self.res.stocks,
            "food_report": food,
            "coverage": cover
        }

# YAML config loader
def load_config(path:str=None):
    if yaml is None or not path or not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as fh:
        cfg = yaml.safe_load(fh) or {}
    # Override seasonal
    if 'seasonal_agri' in cfg:
        SEASONAL_AGRI.update(cfg['seasonal_agri'])
    # Override production rules pairs
    if 'production_rules' in cfg:
        for act, entries in cfg['production_rules'].items():
            if act not in PRODUCTION_RULES:
                PRODUCTION_RULES[act] = full_rule()
            if isinstance(entries, dict):
                for w, val in entries.items():
                    PRODUCTION_RULES[act][w] = val
    # Build events
    specs_by_season = {}
    if 'events' in cfg:
        for season, lst in cfg['events'].items():
            specs = []
            for item in lst:
                eff = item.get('effect', {})
                etype = eff.get('type')
                act = eff.get('activity') or eff.get('flow')
                factor = eff.get('factor', 1.0)
                msg = eff.get('message', item.get('name','Event'))
                def make_effect(etype, act, factor, msg):
                    def _fx(t:'Tribe'):
                        base = t.res.flows.get(act, 0)
                        if etype == 'modify_flow_factor':
                            t.res.flows[act] = int(base * float(factor))
                        elif etype == 'modify_flow_factor_floor':
                            t.res.flows[act] = max(0, int(base * float(factor)))
                        elif etype == 'add_stock':
                            # generic add to tools stock if activity name looks like resource
                            # extend as needed
                            t.res.stocks["🔧"] = t.res.stocks.get("🔧",0) + int(eff.get('amount',0))
                        return msg
                    return _fx
                fx = make_effect(etype, act, factor, msg)
                specs.append(EventSpec(
                    name=item.get('name','custom_event'),
                    probability=float(item.get('probability', item.get('prob', 0.1))),
                    severity=int(item.get('severity', 1)),
                    effect=fx
                ))
            specs_by_season[season] = specs
    return specs_by_season

# LLM advisor helpers
GAME_MASTER_PROMPT = (
    "You are the in-world ADVISOR for a turn-based proto-RTS in the Neolithic.\n"
    "Return a short narrative, a compact status block, 2–4 opportunities, and 3 macro options.\n"
    "Be playful but concise. Do not invent new mechanics.\n"
)

def build_advisor_prompt(report, history, events, last_actions):
    """
    Construit le prompt envoyé au LLM pour jouer le rôle du conseiller.
    """
    # Charger le texte statique
    base_prompt = Path("build_advisor_prompt.md").read_text(encoding="utf-8")
    # Ajouter les infos dynamiques
    dynamic_context = f"""
        # CONTEXTE ACTUEL

        [REPORT COMPACT]
        {report}

        [HISTORIQUE RÉCENT]
        {history}

        [ÉVÉNEMENTS]
        {events}

        [DERNIÈRES ACTIONS DU JOUEUR]
        {last_actions}
        """
    # Prompt final envoyé au LLM
    return base_prompt + "\n" + dynamic_context

def openai_llm_call(prompt:str)->str:
    try:
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"system","content":"You are a concise, lively advisor."},
                        {"role":"user","content": prompt}],
            temperature=0.8, max_tokens=400
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"[LLM fallback] {e}\\nConseiller: Stocke l’excédent, protège les canaux, et prépare des outils pour la moisson. Options: [1] Réaffecter 3 adultes vers 🌾, [2] Investir 🧪 sur filets, [3] Troc peaux↔️pierre."

def render_compact(report:dict, assign:Assignments, demo:Demographics)->str:
    total = report["population_total"]
    workers_adults = demo.men + demo.women_active + demo.grandpas + demo.grandmas
    pop_break = f"{MAN}{demo.men} {WOMAN}{demo.women_active} {PREGNANT}{demo.women_pregnant} {BABY}{demo.babies} {CHILD}{demo.children} {GRANDPA}{demo.grandpas} {GRANDMA}{demo.grandmas}"
    stocks, flows, food = report["stocks"], report["flows"], report["food_report"]
    # food
    store_men = assign.count("🥫", MAN)
    store_cook = assign.count("🥫", SPEC_STORE)
    food_stock = f"🥫 {stocks.get('🥫',0)}(+{food.get('stored',0)})•{MAN}{store_men}{' 🧑‍🍳'+str(store_cook) if store_cook else ''} | ~{max(0, stocks.get('🥫',0)//max(1,food['consumed']))}t / 24"
    food_flow  = f"🍛 +{food['produced']}(-{food['consumed']}) = {food['net']:+d}"
    ag = f"🌾{flows.get('🌾',0)}•" + ''.join([f"{w}{n}" for w,n in assign.per_activity.get('🌾',{}).items()])
    fg = f"🐟{flows.get('🐟',0)}•" + ''.join([f"{w}{n}" for w,n in assign.per_activity.get('🐟',{}).items()])
    hn = f"🦌{flows.get('🦌',0)}•" + ''.join([f"{w}{n}" for w,n in assign.per_activity.get('🦌',{}).items()])
    tools = f"🔧 {stocks.get('🔧',0)}(+{flows.get('🔧',0)})•" + ''.join([f"{w}{n}" for w,n in assign.per_activity.get('🔧',{}).items()])
    sci   = f"🧪 +{flows.get('🧪',0)}•" + ''.join([f"{w}{n}" for w,n in assign.per_activity.get('🧪',{}).items()]) + " (➡️ selon ordres)"
    build = f"🏗 +{flows.get('🏗',0)}•" + ''.join([f"{w}{n}" for w,n in assign.per_activity.get('🏗',{}).items()])
    army  = f"🛡️ {flows.get('🛡️',0)}•" + ''.join([f"{w}{n}" for w,n in assign.per_activity.get('🛡️',{}).items()])
    cov = report["coverage"]
    culture = f"🎭 {cov['🎭']['coverage_pct']}%•" + ''.join([f"{w}{n}" for w,n in assign.per_activity.get('🎭',{}).items()])
    edu     = f"📚 {cov['📚']['coverage_pct']}%•" + ''.join([f"{w}{n}" for w,n in assign.per_activity.get('📚',{}).items()])
    childcare = f"👩‍🍼 {cov['👩‍🍼']['coverage_pct']}%•" + ''.join([f"{w}{n}" for w,n in assign.per_activity.get('👩‍🍼',{}).items()])
    lines = [
        f"👥{total} (💪{workers_adults})",
        pop_break, "——",
        food_stock, food_flow, "{ " + " ".join([ag,"|",fg,"|",hn]) + " }",
        "——", tools, sci, build, army, culture, edu, childcare, "——"
    ]
    return "\\n".join(lines)

HISTORY_PATH="history.md"
def append_history_md(turn:int, compact:str, narrative:str, orders:str, events:list):
    ts = datetime.utcnow().isoformat(timespec="seconds")
    with open(HISTORY_PATH,"a",encoding="utf-8") as f:
        f.write(f"## Tour {turn}  •  {ts} UTC\\n")
        f.write(compact+"\\n\\n")
        f.write("**Conseiller**\\n\\n"+narrative.strip()+"\\n\\n")
        f.write("**Ordres**\\n\\n"+(orders or "(N/A)")+"\\n\\n")
        f.write("**Événements**\\n\\n"+("\\n".join(events) if events else "(aucun)")+"\\n\\n")
        f.write("---\\n")

def run_turn_console(tribe:'Tribe', assign:'Assignments', last_orders:str, inertia:'InertiaTracker', event_engine:'EventEngine', turn:int=1)->None:
    report = tribe.next_turn()
    adjusted = inertia.apply(assign.per_activity, report["flows"])
    report["flows"] = adjusted
    events = event_engine.roll(tribe)
    compact = render_compact(report, assign, tribe.demo)
    prompt = build_advisor_prompt(turn, report, compact, last_orders, events)
    advisor = openai_llm_call(prompt)
    append_history_md(turn, compact, advisor, last_orders, events)
    print("\\n===== TOUR", turn, "=====")
    print(compact)
    print("\\nConseiller >\\n", advisor)
    print("\\nÉvénements >")
    for e in events: print(" -", e)
    print("\\nHistorique:", "history.md")

__all__ = [
    "Demographics","Assignments","Resources","Tribe",
    "EventEngine","EventSpec","InertiaTracker",
    "MAN","WOMAN","PREGNANT","BABY","CHILD","GRANDPA","GRANDMA","KING",
    "SPEC_AGRI","SPEC_FISH","SPEC_STORE","SPEC_TOOLS","SPEC_SCI","SPEC_BUILD","SPEC_ARMY","SPEC_ART","SPEC_EDU","SPEC_ORG","SPEC_NURSE",
    "render_compact","build_advisor_prompt","load_config"
]