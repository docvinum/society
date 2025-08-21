# Points à figer avant code

## 1) Temps et unités

* **Tour = 1 mois**, **année = 12 tours**, saisons = 4 tours chacune.
* **Unités nourriture** = portions par personne par mois.
* **Capacité 🥫** = portions stockables disponibles ce tour.
* **Outils 🔧** = unités abstraites avec usure par usage/turn.
* Documenter ces unités dans `config.yaml` et README.

## 2) Formules clés à préciser

* **Production stockable**: somme des contributions par filière × modificateurs (saison, inertie, événements, difficulté).
* **Consommation**: 1 portion × population totale.
* **Stockage**: `stock_add = clamp(net_food, 0..cap_storage_this_turn)` puis **spoilage** post-stockage (fonction du remplissage et difficulté).
* **Couvertures non stockables**:

  * 👩‍🍼 childcare: % des besoins couverts = f(bébés, capacité). Impacts: natalité future, mortalité infantile si < seuil.
  * 📚 éducation: % enfants couverts = impact à moyen terme sur productivité/qualité des spécialistes (débloqué plus tard).
  * 🎭 culture: % population couverte = cohésion/moral, bonus faible sur productivité si > seuil.
* **Inertie**: cap de réaffectation par filière et malus si dépassement, cooldown N tours.
* **Durabilité outils**: définir l’usure par activité (ex. +1 par 50 points de prod cumulés) et pénalité si 🔧 < seuil.

## 3) Démographie réaliste

* Gestation = **9 tours**. Post-partum = X tours sans concevoir (ex. 2).
* Naissances: probas dépendantes de childcare, rationnement, stress.
* Sevrage simplifié: **bébé -> enfant** après 12 tours.
* Mortalité soft: si déficit alimentaire ≥ K tours consécutifs ou childcare < T%, appliquer un risque modéré.
* Blessés 🤕: retirés de la main d’œuvre pour M tours, n’augmentent pas “danger”.

## 4) Projets multi-tours

* Spécifie comment les **points 🏗** sont générés: contribution par workers affectés à 🏗 + spécialistes 👷 + multiplicateurs outils.
* **Allocation** par projet: `project.allocate(labor, tools)` par tour.
* **Coûts**: déduits quand un jalon est validé, pas au démarrage.
* **Effets partiels**: appliqués immédiatement à la validation du jalon (ex. +capacité 🥫).
* **Pause/Reprise**: conserver la progression du jalon en cours.
* **Annulation**: pas de remboursement par défaut.

## 5) Événements

* Deux couches:
  a) **Événements mécaniques** (YAML) → appliquent des facteurs aux flux / retards / pertes.
  b) **Micro-événements narratifs** (LLM) → texte uniquement, sans effet mécanique.
* Clarifie les **scopes**: “ce tour”, “N tours”, ou “tant que condition”.

## 6) Contrat d’actions JSON (parser)

* **Structure minimale** (existant), ajoute:

  * `assumptions: string[]`
  * `confidence: number`
  * `notes: string[]` (explications du parser)
* **Types d’actions** à lister explicitement:

  * `reassign[{activity, worker, delta}]`
  * `projects[{op, id, labor?, tools?}]`  ops ∈ {start,resume,pause,cancel,allocate}
  * `policies[{name, level}]`  ex. rationing, natality\_encouragement, festival
  * `trade[{with, give:{}, get:{}}]`
  * `rituals[{name, food_cost}]`
* **Clamp** côté validate.py: respecter caps inertie, dispo travailleurs, verrous spécialistes.

## 7) Difficulté réaliste

* Écrire les valeurs par défaut **dans config.yaml** sous `difficulty.presets.realistic`, ce que tu as déjà commencé.
* Ajoute **paliers de sévérité** pour hiver, spoilage et pénalités d’outils.
* Décide si **armée** modifie danger et chasse gros gibier, et comment cela se convertit en flux 🦌.

## 8) Sauvegarde/chargement

* **Versionner** les sauvegardes: `save.version = 1` pour pouvoir migrer plus tard.
* Sauver: état complet, RNG seed, cooldowns inertie, état des projets, preset difficulté, saison/turn.
* Charger: reconstruire les classes, pas juste des dicts.

## 9) UX console

* Affichage compact sur 6 à 8 lignes max, puis un **bloc projets**:

  * `• Granary mk2: active | jalon 2/3 | 45%`
* Choix 1..3 + rappel de **commandes** `:save`, `:load`, `:quit`, `:help`.
* Après input libre → afficher **actions interprétées** puis **actions validées** (clampées) avant application.

## 10) Tests

* `test_engine.py`: prod/conso/stockage/spoilage/inertie.
* `test_projects.py`: progression jalons, pause/reprise, effets.
* `test_parser_contract.py`: schema et clamp.
* `golden tests` de **render\_compact** pour éviter les dérives de format.

# Suggestions d’ajouts à `config.yaml`

* `units:` documenter `food_unit`, `tool_unit`, `turn_length`.
* `spoilage:` règles par saison et seuil de saturation.
* `tool_wear:` par activité.
* `non_stock_thresholds:` seuils de % pour effets (ex. childcare < 60% → natalité--; < 30% → risque).
* `army:` coefficients défense/chasse/gros gibier/pression diplomatique.
* `limits:` `max_workers_per_activity`, `reassign_cap_per_activity`.
* `projects:` inclure `min_labor`, `max_labor` par jalon si tu veux borner le “dump” de main d’œuvre.

# Petites clarifications utiles

* **Spécialistes**: verrouillés dans leur filière, mais peuvent contribuer aux projets via 🏗 si c’est dans la règle? Décide oui/non.
* **Rituels**: coût en 🍞 uniquement, effets narratifs + petits buffs temporaires? Spécifie la durée si buff.
* **Commerce**: le moteur applique ou le LLM? Propose: moteur, via `trade` validé en stocks/flux.

# Prochaines étapes (revues)

1. Finaliser `actions.schema.json` avec `assumptions`, `confidence`, `notes`.
2. Figer les unités et seuils dans `config.yaml` (sections “units”, “spoilage”, “non\_stock\_thresholds”).
3. Lister 3 projets pilotes complets avec jalons, coûts et effets exacts.
4. Décrire 6 à 8 événements mécaniques par saison avec portée et durée.
5. Décider “spécialistes contribuent-ils aux 🏗 projets?” et “armée→chasse gros gibier: quel barème”.

Si tu me valides ces points, je te prépare le **squelette de code final** avec ces décisions intégrées, plus une **boucle console jouable** sur quelques tours. Ready quand tu l’es.
