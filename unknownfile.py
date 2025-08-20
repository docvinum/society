import os, textwrap, json, random
from dataclasses import dataclass, field, asdict
from typing import Dict, Tuple, Callable, Optional, List
from datetime import datetime

# --------- Core constants and helpers (borrowed and trimmed from previous cells) ---------
MAN = "🧔‍♂️"; WOMAN = "👩"; PREGNANT="🤰"; BABY="👶"; CHILD="🧒"; GRANDPA="👴"; GRANDMA="👵"; KING="👑"
SPEC_AGRI="🧑‍🌾"; SPEC_FISH="🎣"; SPEC_STORE="🧑‍🍳"; SPEC_TOOLS="🧑‍🏭"; SPEC_SCI="🧑‍🔬"
SPEC_BUILD="👷"; SPEC_ARMY="💂"; SPEC_ART="🧑‍🎨"; SPEC_EDU="🧑🏻‍🏫"; SPEC_ORG="🧑🏻‍💼"; SPEC_NURSE="👩‍⚕️"
ALL_WORKERS = [MAN, WOMAN, PREGNANT, BABY, CHILD, GRANDPA, GRANDMA, KING,
               SPEC_AGRI, SPEC_FISH, SPEC_STORE, SPEC_TOOLS, SPEC_SCI,
               SPEC_BUILD, SPEC_ARMY, SPEC_ART, SPEC_EDU, SPEC_ORG, SPEC_NURSE]

def full_rule(**kwargs):
    rule = {w: 0 for w in ALL_WORKERS}
    rule.update(kwargs)
    return rule

SEASONAL_AGRI = {"summer": 1.00, "spring": 0.70, "autumn": 0.50, "winter": 0.20}

PRODUCTION_RULES: Dict[str, Dict[str, int]] = {
    "🥫": full_rule(**{MAN:100, SPEC_STORE:500}),
    "🌾": full_rule(**{SPEC_AGRI:30, MAN:10, WOMAN:5, CHILD:5}),
    "🐟": full_rule(**{SPEC_FISH:30, MAN:10, WOMAN:10, CHILD:10}),
    "🦌": full_rule(**{SPEC_ARMY:30, MAN:10, WOMAN:5}),
    "🔧": full_rule(**{SPEC_TOOLS:30, MAN:10, WOMAN:15, CHILD:5}),
    "🧪": full_rule(**{SPEC_SCI:30, MAN:10, WOMAN:10, CHILD:1}),
    "🏗": full_rule(**{SPEC_BUILD:30, MAN:20, WOMAN:5}),
    "🛡️": full_rule(**{SPEC_ARMY:50, MAN:20, WOMAN:5, CHILD:1}),
    "🎭": full_rule(), "📚": full_rule(), "👩‍🍼": full_rule(), "🏛": full_rule(),
}

NON_STOCK_RULES = {
    "🎭": {"capacity": {SPEC_ART:100, MAN:25, WOMAN:25, GRANDPA:25, GRANDMA:25}, "needs":"population_total"},
    "📚": {"capacity": {SPEC_EDU:10, MAN:5, WOMAN:5, GRANDPA:2, GRANDMA:2}, "needs":"children_only"},
    "👩‍🍼": {"capacity": {SPEC_NURSE:5, WOMAN:2, GRANDPA:1, MAN:1, GRANDMA:1}, "needs":"babies_only"},
}

# --------- Data structures ---------
@dataclass
class Demographics:
    men:int=0; women_active:int=0; women_pregnant:int=0; babies:int=0; children:int=0; grandpas:int=0; grandmas:int=0; king:int=0
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
    demo: Demographics; assign: Assignments
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
        return pct, needs, cap

@dataclass
class InertiaTracker:
    last_assignments: Dict[str, Dict[str, int]] = field(default_factory=dict)
    penalty: float = 0.10
    threshold: int = 3
    cooldowns: Dict[str, int] = field(default_factory=dict)  # activity -> turns left
    cooldown_len: int = 2

    def apply(self, current_assignments: Dict[str, Dict[str,int]], flows: Dict[str,int])->Dict[str,int]:
        new_flows = dict(flows)
        for act, now in current_assignments.items():
            prev = self.last_assignments.get(act, {})
            moved = 0
            keys = set(now.keys()) | set(prev.keys())
            for k in keys:
                moved += abs(now.get(k,0) - prev.get(k,0))
            # Start/extend cooldown if exceeded threshold
            if moved > self.threshold:
                self.cooldowns[act] = self.cooldown_len
            # Apply penalty if in cooldown
            if self.cooldowns.get(act,0) > 0 and act in new_flows:
                new_flows[act] = int(new_flows[act] * (1 - self.penalty))
        # Decay cooldowns
        for act in list(self.cooldowns.keys()):
            if self.cooldowns[act] > 0:
                self.cooldowns[act] -= 1
                if self.cooldowns[act] <= 0:
                    self.cooldowns.pop(act, None)
        self.last_assignments = {a: dict(m) for a,m in current_assignments.items()}
        return new_flows

@dataclass
class EventSpec:
    name:str; probability:float; severity:int; effect:Callable[['Tribe'], str]

@dataclass
class EventEngine:
    specs_by_season: Dict[str, List[EventSpec]] = field(default_factory=dict)
    rng: random.Random = field(default_factory=lambda: random.Random(123))

    def roll(self, tribe:'Tribe')->List[str]:
        season = tribe.season
        out = []
        for spec in self.specs_by_season.get(season, []):
            if self.rng.random() < spec.probability:
                out.append(spec.effect(tribe))
        return out

# --------- Tribe engine ---------
@dataclass
class Tribe:
    demo: Demographics; assign: Assignments; res: Resources
    season:str="summer"; king_activity:str="🌾"; king_bonus:float=0.20

    def population_total(self)->int: return self.demo.total

    def compute_stockable_flows(self)->Dict[str,int]:
        flows: Dict[str,int] = {}
        for activity, rule in PRODUCTION_RULES.items():
            if activity in ("🎭","📚","👩‍🍼","🏛"): continue
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
        consumed = self.population_total()  # 1 per person per month
        net = produced - consumed
        # storage capacity this month
        cap = 0
        for w, coef in PRODUCTION_RULES["🥫"].items():
            cap += coef * self.assign.count("🥫", w)
        stored = max(0, min(net, cap))
        self.res.flows["🥫"] = stored
        self.res.flows["🍛_net"] = net
        return {"produced":produced,"consumed":consumed,"net":net,"stored":stored,"capacity":cap}

    def update_stocks(self):
        for res_name in ("🥫","🔧"):
            delta = self.res.flows.get(res_name, 0)
            if delta:
                self.res.stocks[res_name] = self.res.stocks.get(res_name,0) + delta

    def non_stock_coverages(self)->Dict[str,Dict]:
        nsa = NonStockActivity(self.demo, self.assign)
        out={}
        for act in ("🎭","📚","👩‍🍼"):
            pct, needs, cap = nsa.coverage(act)
            out[act] = {"coverage_pct": round(pct,1), "needs": needs, "capacity": cap}
        # simple 🏛 index
        org_points = self.assign.count("🏛", KING) + 2*self.assign.count("🏛", SPEC_ORG)
        out["🏛"] = {"maturity_index": min(100, 20 + org_points*10) if org_points>0 else 10}
        return out

    def next_turn(self)->Dict:
        self.res.flows = self.compute_stockable_flows()
        food = self.compute_food_and_storage()
        self.update_stocks()
        cover = self.non_stock_coverages()
        return {"population_total": self.population_total(), "season": self.season,
                "flows": self.res.flows, "stocks": self.res.stocks,
                "food_report": food, "coverage": cover}

# --------- LLM integration ---------
GAME_MASTER_PROMPT = """You are the in-world ADVISOR for a turn-based proto-RTS in the Neolithic.
Return: 4–6 sentence narrative, then a compact status block, then 2–4 opportunities, then 3 macro options.
Be playful but concise. Do not invent new mechanics.
"""

def build_advisor_prompt(turn:int, tribe_state:Dict, compact_block:str, last_orders:str, events:list)->str:
    payload = {
        "turn": turn, "season": tribe_state.get("season","summer"),
        "state": tribe_state, "compact": compact_block,
        "last_orders": last_orders, "events": events
    }
    return GAME_MASTER_PROMPT + "\n[STATE_JSON]\n" + json.dumps(payload, ensure_ascii=False, indent=2)

def openai_llm_call(prompt:str)->str:
    """
    Real call via OpenAI SDK (requires OPENAI_API_KEY env var).
    Uses gpt-4o-mini by default; adjust as needed.
    """
    try:
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY")
        client = OpenAI(api_key=api_key) if api_key else OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"system","content":"You are a concise, lively advisor."},
                      {"role":"user","content": prompt}],
            temperature=0.8,
            max_tokens=400
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"[LLM fallback] {e}\nConseiller: Stocke l’excédent, protège les canaux, et prépare des outils pour la moisson. Options: [1] Réaffecter 3 adultes vers 🌾, [2] Investir 🧪 sur filets, [3] Troc peaux↔️pierre."

# --------- Render compact automatically ---------
def render_compact(report:Dict, assign:Assignments, demo:Demographics)->str:
    total = report["population_total"]
    workers_adults = demo.men + demo.women_active + demo.grandpas + demo.grandmas  # adults usable (approx)
    # population line 2
    pop_break = f"{MAN}{demo.men} {WOMAN}{demo.women_active} {PREGNANT}{demo.women_pregnant} {BABY}{demo.babies} {CHILD}{demo.children} {GRANDPA}{demo.grandpas} {GRANDMA}{demo.grandmas}"
    # food block
    stocks = report["stocks"]
    flows = report["flows"]
    food = report["food_report"]
    food_stock = f"🥫 {stocks.get('🥫',0)}(+{food.get('stored',0)})•{MAN}{assign.count('🥫',MAN)} {SPEC_STORE if assign.count('🥫',SPEC_STORE) else ''} | ~{max(0, stocks.get('🥫',0)//max(1,food['consumed']))}t / 24"
    food_flow  = f"🍛 +{food['produced']}(-{food['consumed']}) = {food['net']:+d}"
    # food sources
    ag_line = f"🌾{flows.get('🌾',0)}•" + "".join([f"{w}{n}" for w,n in assign.per_activity.get('🌾',{}).items()])
    fish_line = f"🐟{flows.get('🐟',0)}•" + "".join([f"{w}{n}" for w,n in assign.per_activity.get('🐟',{}).items()])
    hunt_line = f"🦌{flows.get('🦌',0)}•" + "".join([f"{w}{n}" for w,n in assign.per_activity.get('🦌',{}).items()])
    food_sources = " | ".join([ag_line, fish_line, hunt_line])
    # tools/sci/build/army
    tools = f"🔧 {stocks.get('🔧',0)}(+{flows.get('🔧',0)})•" + "".join([f"{w}{n}" for w,n in assign.per_activity.get('🔧',{}).items()])
    sci   = f"🧪 +{flows.get('🧪',0)}•" + "".join([f"{w}{n}" for w,n in assign.per_activity.get('🧪',{}).items()]) + " (➡️ selon ordres)"
    build = f"🏗 +{flows.get('🏗',0)}•" + "".join([f"{w}{n}" for w,n in assign.per_activity.get('🏗',{}).items()])
    army  = f"🛡️ {flows.get('🛡️',0)}•" + "".join([f"{w}{n}" for w,n in assign.per_activity.get('🛡️',{}).items()])
    # coverage (%)
    cov = report["coverage"]
    culture = f"🎭 {cov['🎭']['coverage_pct']}%•" + "".join([f"{w}{n}" for w,n in assign.per_activity.get('🎭',{}).items()])
    edu     = f"📚 {cov['📚']['coverage_pct']}%•" + "".join([f"{w}{n}" for w,n in assign.per_activity.get('📚',{}).items()])
    childcare = f"👩‍🍼 {cov['👩‍🍼']['coverage_pct']}%•" + "".join([f"{w}{n}" for w,n in assign.per_activity.get('👩‍🍼',{}).items()])
    # assemble
    lines = [
        f"👥{total} (💪{workers_adults})",
        pop_break,
        "——",
        food_stock,
        food_flow,
        "{ " + " ".join([ag_line, "|", fish_line, "|", hunt_line]) + " }",
        "——",
        tools,
        sci,
        build,
        army,
        culture,
        edu,
        childcare,
        "——"
    ]
    return "\n".join(lines)

# --------- History ---------
HISTORY_PATH = "/mnt/data/history.md"
def append_history_md(turn:int, compact:str, narrative:str, orders:str, events:list):
    ts = datetime.utcnow().isoformat(timespec="seconds")
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(f"## Tour {turn}  •  {ts} UTC\n")
        f.write(compact + "\n\n")
        f.write("**Conseiller**\n\n" + narrative.strip() + "\n\n")
        f.write("**Ordres**\n\n" + (orders or "(N/A)") + "\n\n")
        f.write("**Événements**\n\n" + ("\n".join(events) if events else "(aucun)") + "\n\n")
        f.write("---\n")

# --------- Advisor runner ---------
def run_turn_console(tribe:'Tribe', assign:'Assignments',
                     last_orders:str, inertia:'InertiaTracker', event_engine:'EventEngine',
                     turn:int=1)->None:
    report = tribe.next_turn()
    # inertia
    adjusted = inertia.apply(assign.per_activity, report["flows"])
    report["flows"] = adjusted
    # events
    events = event_engine.roll(tribe)
    # render compact
    compact = render_compact(report, assign, tribe.demo)
    # advisor
    prompt = build_advisor_prompt(turn, report, compact, last_orders, events)
    advisor_text = openai_llm_call(prompt)
    # log
    append_history_md(turn, compact, advisor_text, last_orders, events)
    # console out
    print("\n===== TOUR", turn, "=====")
    print(compact)
    print("\nConseiller >\n", advisor_text)
    print("\nÉvénements >")
    for e in events:
        print(" -", e)
    print("\nHistorique:", "/mnt/data/history.md")

# --------- Demo wiring ---------
def demo_setup_and_run():
    # Demographics sample
    demo = Demographics(men=26, women_active=10, women_pregnant=21, babies=24, children=18, grandpas=2, grandmas=1, king=1)
    # Assignments sample
    assign = Assignments(per_activity={
        "🌾": {MAN:10, SPEC_AGRI:2, KING:1},
        "🐟": {SPEC_FISH:1, CHILD:6},
        "🦌": {SPEC_ARMY:3},
        "🥫": {MAN:3},
        "🔧": {MAN:3},
        "🧪": {MAN:3},
        "🏗": {MAN:3},
        "🛡️": {SPEC_ARMY:1},
        "🎭": {MAN:3},
        "📚": {MAN:1, WOMAN:1, GRANDPA:1, GRANDMA:1},
        "👩‍🍼": {WOMAN:8, SPEC_NURSE:1, GRANDPA:1, GRANDMA:1},
        "🏛": {KING:1}
    })
    res = Resources(stocks={"🥫":1519, "🔧":100})
    tribe = Tribe(demo=demo, assign=assign, res=res, season="summer", king_activity="🌾", king_bonus=0.20)

    # Events with probabilities & severity
    def ev_boost_forage(t:Tribe)->str:
        t.res.flows["🐟"] = int(t.res.flows.get("🐟",0) * 1.2)
        return "Abondance de baies et poissons: 🐟 +20% ce tour."
    def ev_canal_clog(t:Tribe)->str:
        t.res.flows["🌾"] = max(0, int(t.res.flows.get("🌾",0) * 0.9))
        return "Canaux partiellement colmatés: 🌾 -10% ce tour sans maintenance."
    def ev_wolves(t:Tribe)->str:
        t.res.flows["🛡️"] = int(t.res.flows.get("🛡️",0) * 1.1)
        return "Loups rôdent: 🛡️ vigilance accrue (+10%)."

    event_engine = EventEngine(specs_by_season={
        "summer":[
            EventSpec("forage_boom", 0.35, 1, ev_boost_forage),
            EventSpec("canal_clog", 0.30, 2, ev_canal_clog),
            EventSpec("wolves", 0.25, 1, ev_wolves),
        ]
    })

    inertia = InertiaTracker(penalty=0.10, threshold=3, cooldown_len=2)
    run_turn_console(tribe, assign, "Renforcer stockage et patrouilles.", inertia, event_engine, turn=1)
