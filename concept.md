Voici l’architecture, la logique et le process de jeu pour une version console hybride moteur+LLM, où chacun fait ce qu’il sait faire de mieux.

# Arborescence du projet

```
society/
  assets/
    config.yaml                # barèmes, saisons, événements, difficultés, projets
    examples/
      sample_save.json
  src/
    engine/
      __init__.py
      model.py                 # état du monde: Demographics, Assignments, Resources, Projects, TribeState
      rules.py                 # barèmes de prod, saison, coûts, limites, durabilité outils
      difficulty.py            # presets de difficulté, modificateurs réalistes
      projects.py              # logique projets multi-tours, jalons, pause, reprise, annulation
      events.py                # EventSpec, EventEngine, effets mécaniques
      inertia.py               # inertie avec cooldown par filière et cap de réaffectation par tour
      sim.py                   # step(): applique actions validées, calcule flux, stock, natalité, mortalité soft
      validate.py              # validation des actions JSON, clamp, feedback
      io_state.py              # sauvegarde, chargement, history.md, snapshots
      render.py                # render_compact(), vues console pour choix et feedback
      config.py                # charge YAML, fusionne overrides, expose accès typé
    llm/
      advisor.py               # conseiller: prompt builder + appel LLM
      parser.py                # interprète les ordres libres → actions JSON chiffrées
      prompts/
        advisor_master.md
        parser_master.md
        style_guidelines.md    # adaptation au ton du joueur
      schemas/
        actions.schema.json    # contrat JSON entre parser LLM et moteur
    cli/
      game.py                  # boucle interactive multi-tours, input libre + choix 1..3
      commands.py              # :save, :load, :quit, :config, :help
      colors.py                # helpers couleurs/emoji console
  tests/
    test_engine.py             # prod, conso, stockage, saison, inertie
    test_projects.py           # jalons, pause, reprise, annulation
    test_parser_contract.py    # conformité au schema JSON
  README.md
  INSTALL.md
  requirements.txt
  LICENSE
```

# Logique du code

## 1) Moteur (déterministe)

* `rules.py`

  * Tables de production par filière et type de personne.
  * Multiplicateurs saisonniers.
  * Coûts de projets éventuels.
  * Limites de stockage.
* `model.py`

  * État du monde: démographie, affectations par filière, ressources, saison, indicateurs non stockables (childcare, culture, éducation).
* `sim.py`

  * `step(state, actions, rng)`

    * Applique les **actions validées** (réaffectations, projets si coûts ok, politiques).
    * Calcule les **flux** (prod, conso), applique **stockage** et **capacités**.
    * Applique **inertie** et **événements** mécaniques du tour.
    * Met à jour démographie (naissances, sevrage simple, mortalité si conditions critiques).
    * Retourne `report` + `state` mis à jour.
* `events.py`

  * Système d’événements paramétrés via YAML. Les effets ont un **impact mécanique explicite** (ex: facteur sur 🌾 ce tour).
  * Le LLM peut raconter des micro-événements, mais seuls ceux validés par `events.py` modifient l’état.
* `inertia.py`

  * Pénalité quand on bouge trop de monde trop vite, avec **cooldown par filière**.
* `validate.py`

  * Schéma JSON des actions possibles.
  * Vérifie coûts, nombres entiers, limites de main d’œuvre, verrouillage des spécialistes.
  * Toute action non valide est rejetée ou tronquée proprement.

## 2) LLM (créatif et interprétatif)

* `llm/advisor.py`

  * Construit un prompt avec `advisor_master.md` + `[COMPACT]` + `[STATE_JSON]` + `[HISTO]` + `[EVENTS]` + `[LAST_ORDERS]`.
  * Retourne un texte structuré avec balises `[NARRATION] [BILAN] [OPPORTUNITÉS] [CHOIX]`.
* `llm/parser.py`

  * Construit un prompt avec `parser_master.md`, l’**entrée libre du joueur**, et l’**état JSON**.
  * Retour JSON d’**actions canoniques** selon un **schema** partagé (réaffectations, projets, politiques, troc).
  * Fallback si le LLM échoue: micro-parser règles simples.

## 3) Console

* `cli/game.py`

  * Boucle interactive.
  * Affiche `render_compact(report)`.
  * Appelle le conseiller pour proposer 3 choix.
  * Accepte soit un numéro (1..3), soit une **entrée libre**.
  * Passe l’entrée libre au **parser LLM** → JSON d’actions.
  * Valide via `validate.py`, applique via `sim.step()`.
  * Supporte `:save file.json`, `:load file.json`, `:quit`.
* `cli/commands.py`

  * Petites commandes utilitaires.
* `engine/io_state.py`

  * Sauvegardes, rechargements, `history.md` enrichi par tour.

## 4) Difficulté réaliste

`difficulty.py` définit un preset réaliste appliqué partout:

* **Nourriture**: spoilage mensuel si capacité 🥫 insuffisante ou chaleur estivale. Exemple: base 2% par mois, +3% en été si stockage saturé.
* **Hiver**: multiplicateurs négatifs sur 🌾, bonus modeste sur chasse si faune locale, besoins en 🔧 pour tenues et outils.
* **Outils**: durabilité décroît par usage. Pénalités si 🔧 < seuil.
* **Natalité**: gestation 9 tours, récupération post-partum. Fertilité modulée par childcare et rationnement.
* **Mortalité soft**: risques accrus si déficit alimentaire ou childcare bas sur plusieurs tours. Jours d’arrêt pour blessés 🤕 hors main d’oeuvre.
* **Inertie**: cap de réaffectation par filière et tour (ex. 5 adultes), malus 10 à 20% si dépassement, cooldown 2 tours.

Toutes ces valeurs viennent de `config.yaml` via un bloc `difficulty.presets.realistic`.

## 2) Projets multi-tours

`projects.py` gère des **ProjectSpec** définis en YAML:

* Champs: `id`, `label`, `milestones` avec coût par jalon en 🪵, 🪨, 🔧, points de **🏗 construction** par jalon, main d’oeuvre minimale, dépendances, bonus partiels à chaque jalon.
* États: `planned`, `active`, `paused`, `completed`, `cancelled`.
* Actions supportées: `project.start`, `project.pause`, `project.resume`, `project.cancel`, `project.allocate(labor=..., tools=...)`.
* Effets: à chaque step, les points 🏗 alloués convertissent en progression de jalon, consomment ressources et durabilité d’outils. Certains projets débloquent capacités immédiates dès un jalon atteint, par exemple:

  * Silo 1: +capacité 🥫
  * Tour de guet 1: +défense passive, patrouilles plus efficaces
  * Irrigation 1: multiplicateur 🌾 en saison chaude

`sim.step()` fait avancer tous les projets actifs selon l’allocation et applique les gains.

## 3) Parser LLM avec réallocation chiffrée automatique

`llm/parser.py` traduit l’input libre en **actions JSON canoniques** et **chiffre** même si le joueur est ambigu:

* Heuristique: si le joueur dit « renforcer les champs », le parser propose `reassign` avec un **delta** estimé pour 🌾, borné par les caps de difficulté et la main d’oeuvre disponible.
* Le parser doit retourner:

  * `actions` respectant `actions.schema.json`
  * `assumptions`: texte court listant les inférences et seuils utilisés
  * `confidence`: 0.0 à 1.0
* Exemple d’actions JSON:

```json
{
  "reassign": [{"activity": "🌾", "worker": "🧔‍♂️", "delta": 3}],
  "projects": [{"op": "allocate", "id": "granary_mk2", "labor": 4}],
  "policies": [{"name": "rationing", "level": 1}],
  "trade": [],
  "rituals": []
}
```

`validate.py` filtre, **clamp** les deltas, verrouille les spécialistes à leur filière, renvoie des `notes` pour tout ce qui est ajusté.

## 4) Conseiller LLM

`llm/advisor.py`:

* Construit un prompt avec `advisor_master.md`, le **render compact**, l’`STATE_JSON`, l’historique récent et les événements.
* Produit un texte balisé `[NARRATION] [BILAN] [OPPORTUNITÉS] [CHOIX]` avec 3 choix.
* Le ton s’adapte au style détecté du joueur via `style_guidelines.md` et indices simples (ponctuation, émojis, vocabulaire).

## 5) Moteur de simulation

`sim.py` applique dans cet ordre:

1. **Actions validées**: réaffectations bornées, allocations de projet, politiques.
2. **Inertie**: cap et malus par filière si changement trop brutal.
3. **Production stockable**: calcule 🌾, 🐟, 🦌 avec effets saisonniers et difficultés.
4. **Consommation**: 1 portion par personne. Calcul du **net** et stockage réel limité par 🥫 ce tour.
5. **Spillage et durabilité**: spoilage aliments, usure 🔧 selon usage.
6. **Non stockables**: couverture 👩‍🍼, 🎭, 📚 en %. Effets sur fertilité, moral, cohésion.
7. **Projets**: progression, consommation de ressources, bonus jalons.
8. **Événements mécaniques**: tirages YAML, facteurs sur flux, retards de jalon, blessés.
9. **Démographie**: natalité selon seuils, sevrage, mortalité soft en cas de pénurie.
10. **Rapport**: objet `Report` avec `flows`, `stocks`, `coverage`, `projects_status`, `notes`.

## 6) Console

`cli/game.py`:

* Affiche le **compact** et l’état des **projets** (ligne par projet: état, jalon en cours, %).
* Appelle le **conseiller** pour narration et 3 choix.
* Demande **input**: un numéro 1..3, un texte libre, ou une commande.
* Passe le texte libre au **parser** pour actions JSON.
* Affiche un **récapitulatif** des actions interprétées et clampées avant application.
* Applique `sim.step()` et journalise via `io_state.append_history`.

# Process de jeu

1. **Initialisation**

   * Charger `config.yaml` et le preset `difficulty.realistic`.
   * Créer `TribeState`, initialiser projets disponibles, EventEngine, InertiaTracker.
   * Si `:load`, restaurer l’état et l’historique.

2. **Boucle de tour**

   * Calculer et afficher `render_compact(state)` avec ressources, flux, couvertures, projets.
   * Obtenir le texte du **conseiller** avec 3 **choix** numérotés.
   * Lire l’**entrée joueur**:

     * `1..3`: choix proposé
     * Texte libre: intentions naturelles
     * Commandes: `:save`, `:load`, `:quit`, `:config`
   * Parser input → **actions JSON** chiffrées. Valider → **actions validées** + `notes`.
   * Appliquer `sim.step(state, actions_validées)`.
   * Afficher résultats du tour, événements, jalons atteints, notes de validation.
   * Historiser: compact, conseiller, actions, notes, événements, snapshot léger.

3. **Tour n+1**

   * Répéter. Le LLM peut adapter son ton et ses conseils à ton style et aux tendances du village.

4. **Sauvegarde et reprise**

   * `io_state.save(filename)`: sérialise état, projets, inertie, RNG, difficulté, version.
   * `io_state.load(filename)`: restaure l’ensemble.

5. **Fin de partie**

   * Libre. Tu pourras plus tard ajouter objectifs, conditions de victoire, métriques de prospérité.
   * Si toute la population meurt.
   * Si la population se rebelle contre le chef de tribu (joueur) et le détrone ou le tue.

# Pourquoi cette séparation est optimale

* Le **monde** est simulé par un moteur reproductible et testable.
* Le **LLM** gère narration, interprétation du langage naturel, et propose des options stylées.
* Le **contrat d’actions JSON** au milieu débruite les entrées, garde la sécurité, et facilite les tests.
* YAML permet de tuner les barèmes et événements sans recompilation.
* La console reste fluide, avec sauvegarde/chargement et historique clair.

# Détails clés à figer dans `config.yaml`

* `difficulty.presets.realistic`: tous les coefficients cités plus haut.
* `projects`: specs avec jalons et effets partiels.
* `events`: liste par saison, probas, sévérité, effets mécaniques autorisés.
* `limits`: cap de réaffectation par filière et par tour, max workers par filière, tailles de stock.
* `production`: barèmes par type de travailleur, spécialisés inclus.
* `organization`: coefficients culture, éducation, childcare sur cohésion, fertilité, risques.

# Prochaines étapes

1. Figer le **contrat JSON d’actions** dans `llm/schemas/actions.schema.json`.
2. Rédiger `parser_master.md` avec règles d’inférence chiffrée et limites à respecter.
3. Écrire les premiers **ProjectSpec**: irrigation, grand grenier, palissade, tour de guet.
4. Définir les **paramètres réalistes** dans `config.yaml`.
