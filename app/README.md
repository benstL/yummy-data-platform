🇫🇷 [Version française](#version-française) · 🇬🇧 [English version](#english-version)

---

## 🇫🇷 Version française

# YUMMY Interface Streamlit — Documentation technique

> **Chiffres issus de l'exécution canonique du 2026-05-28** (voir `ml/README.md` pour les détails du pipeline).

> **Fichier :** `app/streamlit_app.py`  
> **Lancement :** `streamlit run app/streamlit_app.py`  
> **Port par défaut :** 8501 (auto-incrémentation si occupé)

---

### 1. Vue d'ensemble

L'interface YUMMY est une application Streamlit monopage qui recommande des recettes personnalisées selon le pays de l'utilisateur, le mois courant et un panier d'ingrédients de saison sélectionnés.

**Pourquoi des lectures directes de parquets (et non FastAPI) pour la démo :**

| Préoccupation | Choix démo | Choix V2 |
|---|---|---|
| Latence | `@st.cache_data` charge les parquets une fois par session (~2 s au démarrage à froid, <1 ms en cache) | FastAPI sert des données pré-chargées avec des en-têtes de cache HTTP |
| Simplicité de déploiement | Commande unique `streamlit run`, aucun processus API distinct | Deux processus + répartiteur de charge |
| Démo hors ligne | Fonctionne sans réseau | Nécessite une API en cours d'exécution |
| Observabilité | Aucune | Middleware API pour la journalisation des requêtes et le suivi de la latence |

Le FastAPI (`api/main.py`) existe et expose `GET /recommendations`, enrichi de la durabilité (pays × mois) depuis le commit de Sarah. Il couvre 2 des 5 sources agrégées par `build_merged()` : recommandations et durabilité. Les 3 sources restantes (clusters, carte d'ingrédients, panier saisonnier) sont lues directement par Streamlit.
`app/streamlit_app.py` est intentionnellement découplé pour la stabilité de la démo.

**Chemin de migration V2 (5 chantiers, pas un drop-in) :** servir l'app entièrement via l'API nécessite :
1. `GET /basket-recommendations?country=&month=&basket=` — filtrage sur `matched_ingredients`, retournant aussi `cluster_label` et `matched_ingredients` dans le payload ;
2. `GET /seasonal-products?country=&month=` — produits EUFIC en saison (aujourd'hui lu depuis Silver) ;
3. `GET /faostat-staples?country=` — aliments de base FAOSTAT (aujourd'hui lu depuis Silver) ;
4. `GET /countries` — liste des pays disponibles (EUFIC ∪ FAOSTAT) ;
5. Ajout de `cluster_label` et `matched_ingredients` au join interne de l'API.

La logique panier (intersection EUFIC×mois / FAOSTAT, bandeau de confiance) reste aujourd'hui côté Streamlit.

---

### 2. Parcours utilisateur

```
┌─────────────────────────────────────────────────────────────────┐
│  Step 1 — Language                                               │
│  Select 🇫🇷 Français or 🇬🇧 English (sidebar (left))            │
│  All UI strings switch immediately; ML cluster labels stay EN.   │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 2 — Context                                                │
│  Pick Country (273 options) + Month (Jan–Dec, default June).     │
│  A confidence banner appears immediately below showing whether   │
│  EUFIC 🟢, FAOSTAT 🟡, or neither 🔴 has data for that country. │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 3 — Ingredient basket                                      │
│  Multiselect pre-populated with up to 3 items from:             │
│   - EUFIC in-season products (country × month) → 🟢 items       │
│   - FAOSTAT top-produced staples (latest year) → 🟡 items       │
│  User can add, remove, or keep defaults.                         │
│  Always pre-selected (never empty) — see §3.3.                   │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 4 — Cluster filter (optional)                              │
│  Multiselect with all 5 cluster labels checked by default.       │
│  Deselect any cluster to narrow results to recipe type.          │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 5 — Generate                                               │
│  Click "🍽️ Generate Recommendations" (full-width primary button)│
│  If basket is empty → warning, no results shown.                 │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 6 — Filtres post-génération                               │
│  Slider "⏱️ Temps max" : 10–180 min (défaut 60, pas 5).        │
│  Radio "Trier par" : Score Yummy · Score Durabilité ·           │
│  Meilleur compromis (0,6 × Yummy + 0,4 × Durabilité).          │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 7 — Aperçu des résultats                                  │
│  4 métriques agrégées : nb recettes · score Yummy moyen ·       │
│  score Durabilité moyen · temps moyen.                          │
│  + 2 expanders "Comprendre le Score" (Yummy / Durabilité).      │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 8 — Cartes recettes                                       │
│  Top 10 selon le tri choisi. Chaque carte : nom, catégorie,     │
│  médaille 🥇/🥈/🥉 (rang 1–3), Score Yummy + barre,           │
│  Durabilité + badge (🌱/🌿/🟡/🔴) + barre, note, temps,       │
│  badge cluster, indicateur saison 🟢/🟡, légende.              │
│  Expander "📖 Détails de la recette" : saisonnalité,            │
│  disponibilité agricole et couverture (/100) + ingrédients.     │
└─────────────────────────────────────────────────────────────────┘
```

---

### 3. Fonctionnalités

#### 3.1 Bandeau de confiance

Immédiatement après la sélection du pays et du mois, un bandeau en forme de pastille apparaît :

| Condition | Couleur | Message |
|---|---|---|
| Pays dans EUFIC | 🟢 teinte verte | « Reliable seasonal data (EUFIC) » |
| Pays dans FAOSTAT uniquement | 🟡 teinte ambrée | « Agricultural availability proxy (FAOSTAT) » |
| Aucun des deux | 🔴 teinte rouge | « Limited data — low confidence » |

EUFIC couvre 29 pays européens ; FAOSTAT couvre 244 pays/régions.

#### 3.2 Enrichissement du panier saisonnier

Le panier combine deux sources pour garantir que même les pays non couverts par EUFIC disposent d'ingrédients pré-sélectionnés :

```python
eufic_items  = get_seasonal_products(country, month)  # EUFIC in-season
faostat_only = [p for p in get_faostat_staples(country)
                if p not in set(eufic_items)]          # FAOSTAT, deduped
all_options  = eufic_items + faostat_only
```

Les catégories agrégées FAOSTAT (« vegetables primary », « meat, total », etc.) sont exclues par un filtre par mots-clés avant présentation à l'utilisateur.

#### 3.3 Comportement de sélection par défaut

```python
default_basket = all_options[:3]   # always the first 3 available items
```

Cela garantit que le multiselect n'est jamais vide au rendu initial, même pour les pays sans données EUFIC (ex. : le Gabon affiche les aliments de base FAOSTAT). L'utilisateur doit effacer manuellement la sélection pour déclencher l'avertissement « aucun ingrédient ».

#### 3.4 Filtre par cluster

Les 5 clusters sont sélectionnés par défaut (aucun filtrage). Si l'utilisateur désélectionne des clusters et que l'intersection avec les résultats du panier est vide, le filtre de cluster est silencieusement ignoré et les résultats du panier sont affichés inchangés, accompagnés d'un message d'information expliquant le repli.

#### 3.5 Bascule de langue FR/EN

Le système i18n est implémenté comme un simple dictionnaire Python :

```python
TEXTS = {
    "fr": { "title": "🍽️ YUMMY", "btn_generate": "🍽️ Générer…", … },
    "en": { "title": "🍽️ YUMMY", "btn_generate": "🍽️ Generate…", … },
}
lang = st.selectbox(…)   # "fr" or "en"
texts = TEXTS[lang]      # all subsequent UI strings use texts["key"]
```

**Pourquoi pas gettext / GNU i18n :**  
L'application comporte ~35 chaînes traduisibles, toutes codées en dur dans un seul fichier. gettext ajoute une complexité de build (fichiers `.po` / `.mo`, outillage d'extraction) sans bénéfice à cette échelle. Un dictionnaire simple est transparent, versionné et refactorable en quelques secondes.

**Les étiquettes de clusters ne sont intentionnellement pas traduites.** Elles constituent la sortie de la taxonomie ML (colonne `cluster_label` dans les parquets Gold) et servent de contrat d'interface entre les couches ML et UI — les traduire briserait ce contrat et nécessiterait un ré-étiquetage des parquets.

#### 3.6 Filtre de temps de préparation

Après génération, un slider permet de restreindre les résultats :

```python
max_time = st.slider("⏱️ Temps maximum de préparation", min_value=10, max_value=180, value=60, step=5)
cluster_results = cluster_results[cluster_results["totaltime"].fillna(999) <= max_time]
```

Les recettes sans `totaltime` (valeur `NaN`) sont traitées comme ayant 999 min et exclues dès que le slider passe en dessous de 999. Le filtre est appliqué avant le tri.

#### 3.7 Mode de tri des résultats

Un radio à 3 options (horizontal) apparaît après le slider :

| Option | Comportement |
|---|---|
| **Score Yummy** | `sort_values("yummy_score", ascending=False)` |
| **Score Durabilité** | `sort_values("durability_score", ascending=False)` |
| **Meilleur compromis** | `0.6 × yummy_score + 0.4 × durability_score`, trié décroissant |

> **Note :** les tris « Score Durabilité » et « Meilleur compromis » s'appuient sur `durability_score` chargé depuis la partition `durability_country=<pays>` pour le mois sélectionné — le score reflète le pays et le mois de l'utilisateur (voir `ml/README.md §7.4`).

#### 3.8 Aperçu des résultats

Affiché après le tri, avant les cartes :

```python
st.subheader("📊 Aperçu des résultats")
# 4 colonnes : nb recettes · score Yummy moyen · score Durabilité moyen · temps moyen
```

Suivi de deux expanders :
- **Comprendre le Score Yummy** : composantes (note, popularité, simplicité, sentiment).
- **🌍 Comprendre le Score de Durabilité** : formule (75 % saisonnalité + 25 % disponibilité, bonus ≥ 2/3).

#### 3.9 Détails de la recette

Chaque carte recette dispose d'un expander `📖 Détails de la recette` qui expose :

- 🌱 **Saisonnalité** : `seasonality_score / 100`
- 🌾 **Disponibilité agricole** : `availability_score / 100`
- 🎯 **Couverture** : `coverage_score / 100`
- 🧺 Liste des ingrédients reconnus (`matched_ingredients`)

---

### 4. Logique de recommandation

#### 4.1 Intersection panier → recettes

```python
def _ingredient_hits(ingredients: set[str], basket_set: set[str]) -> set[str]:
    hits = set()
    for b in basket_set:
        for i in ingredients:
            if b in i or i in b:    # bidirectional substring match
                hits.add(b)
                break
    return hits
```

**Pourquoi la correspondance par sous-chaîne (et non exacte) :**  
La colonne `matched_ingredients` Gold stocke des termes de référence appariés par TF-IDF, qui peuvent différer lexicalement des éléments du panier EUFIC :

| Élément du panier EUFIC | Valeur `matched_ingredients` | Correspondance exacte ? | Sous-chaîne ? |
|---|---|---|---|
| `"aubergine"` | `"eggplants (aubergines)"` | ✗ | ✓ |
| `"tomato"` | `"tomato"` | ✓ | ✓ |
| `"garlic"` | `"garlic"` | ✓ | ✓ |

#### 4.2 Classement

Les recettes qualifiées sont triées par ordre décroissant de `yummy_score` et le top 10 est retourné.
`yummy_score` est un composite ajusté de façon bayésienne (voir `ml/README.md §6` pour la formule).

**Exemple concret — France, juillet, panier = `['apricot', 'artichoke', 'aubergine']` :**
- **3,711** recettes qualifiées (correspondance par sous-chaîne dans `matched_ingredients`)
- Résultat n°1 : *Caponata Eggplant And Lots Of Good Things* — WR 4.834, 9 avis, sentiment rétréci 76.96, yummy\_score **72.64**
- Tous les résultats du top 10 ont 6–23 avis et WR ≥ 4.79 — aucune valeur aberrante avec peu d'avis (exécution canonique du 2026-05-28 ; tableau complet dans `ml/README.md §5.4`)

#### 4.3 Ligne d'explicabilité

Chaque carte affiche une légende en texte brut nommant les ingrédients réellement appariés :

```
"Recommended because: popular (9 reviews), ready in 25 min, matches: aubergine, artichoke."
```

Composants affichés uniquement s'ils sont non nuls :
- `popular (N reviews)` — issu de `reviewcount`
- `ready in T min` — issu de `totaltime`
- `matches: X, Y` — intersection du panier de l'utilisateur avec `matched_ingredients`

#### 4.4 Niveaux de repli

```
Tier 1 (normal):    basket_set ∩ matched_ingredients  →  results
                              ↓ empty
Tier 2 (selection fallback):  all_options ∩ matched_ingredients  →  results
                              + info: "No recipe matches your exact selection"
                              ↓ empty
Tier 3 (global fallback):     global top-N sorted by yummy_score
                              + info: "No recipes found matching your basket"
```

Au Niveau 2, la ligne d'explicabilité est remplacée par un message honnête (« no selection — top seasonal picks ») plutôt que d'inventer des correspondances d'ingrédients ne correspondant pas à la sélection réelle de l'utilisateur.

---

### 5. Design UI/UX

#### 5.1 Thème — `.streamlit/config.toml`

```toml
[theme]
primaryColor             = "#F4A261"   # warm amber (spice/curry tone)
backgroundColor          = "#111118"   # near-black, warm dark base
secondaryBackgroundColor = "#1A1A22"   # card backgrounds
textColor                = "#E8E8E3"   # warm off-white
font                     = "sans serif"
```

Poppins (Google Fonts, 400/500/600/700) est chargé via du CSS injecté et remplace le fallback `font = "sans serif"` pour tout le texte visible.

#### 5.2 Approche d'injection CSS

```python
def inject_css() -> None:
    st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)
```

`inject_css()` est appelé une fois au début de `main()`. Le bloc `<style>` est ajouté au `<head>` de la page Streamlit et s'applique globalement.

**Risque de couplage de version :** La structure HTML de Streamlit (noms de classes CSS comme `.block-container`, attributs data-testid) peut changer entre les versions mineures. Le CSS utilise un mélange de sélecteurs sémantiques stables (`.main .block-container`) et de sélecteurs data-testid pour les ajustements au niveau des widgets. Si les mises à jour de Streamlit cassent un sélecteur, seul le style de ce widget est affecté — la mise en page et la logique restent intactes. L'épinglage de la version Streamlit dans `requirements.txt` atténue ce risque.

#### 5.3 Design des cartes

Les cartes de recettes sont rendues en HTML injecté via `st.markdown(unsafe_allow_html=True)` :

```
┌──────────────────────────────────────────────── 🟢 ─┐
│  Recipe Name (bold, 1.05rem)                          │
│  [category tag]                                       │
│─────────────────────────────────────────────────────│
│  YUMMY SCORE │ RATING  │ TIME    │ CLUSTER           │
│  72.6/100    │ 4.8/5   │ 25 min  │ [⚡ Quick & Easy] │
│  ████████░░░                                          │  ← gradient progress bar
│─────────────────────────────────────────────────────│
│  Recommended because: popular (9 reviews),            │
│  ready in 25 min, matches: aubergine.                 │
└──────────────────────────────────────────────────────┘
```

- Survol : `transform: translateY(-2px)` + ombre plus prononcée — CSS uniquement, zéro JS
- Barre de progression : style inline `width: {yummy}%` plafonné à 100

**Couleurs des badges de cluster :**

| Cluster | Classe du badge | Couleur |
|---|---|---|
| 🏆 Top Rated | `badge-top` | Amber `#FCD34D` on tinted bg |
| ⭐ Crowd Favourite | `badge-crowd` | Blue `#93C5FD` |
| ⚡ Quick & Easy | `badge-quick` | Green `#6EE7B7` |
| 🌿 Seasonal & Local | `badge-seasonal` | Teal `#5EEAD4` |
| 🌍 Global Kitchen | `badge-global` | Purple `#C4B5FD` |

#### 5.4 Pourquoi Streamlit natif plutôt que des bibliothèques de composants tiers

| Préoccupation | Décision |
|---|---|
| Risque de dépendance | Les composants Streamlit tiers dépendent des versions React et peuvent casser lors des mises à jour de Streamlit |
| Complexité de build | Les composants personnalisés nécessitent une chaîne d'outils Node.js |
| Démo hors ligne | Les composants CDN externes échouent sans réseau |
| Contrôle suffisant | L'injection CSS + `unsafe_allow_html` sur `st.markdown` offre un contrôle complet au niveau des cartes |

Tous les widgets interactifs (multiselect, selectbox, button, spinner, expander) restent natifs Streamlit. Seuls les éléments d'affichage utilisent du HTML injecté.

---

### 6. Contrats de données

Les colonnes listées ici constituent l'**interface entre le pipeline ML et l'interface**. Tout changement de nom ou de type de colonne dans les parquets Gold doit être répercuté ici.

#### Chargé par `app/streamlit_app.py`

**`gold_yummy_recommendations.parquet`** (via `load_recommendations()`)

| Colonne | Type | Utilisé pour |
|---|---|---|
| `recipeid` | int64 | Clé de jointure |
| `name` | str | Titre de la carte |
| `recipecategory` | str | Étiquette de catégorie de la carte |
| `totaltime` | int64 | Métrique de temps, explicabilité |
| `aggregatedrating` | float64 | Métrique de note |
| `reviewcount` | float64 | Ligne d'explicabilité |
| `yummy_score` | float64 | Classement + barre de progression |

**`gold_recipe_clusters.parquet`** (via `load_clusters()`)

| Colonne | Type | Utilisé pour |
|---|---|---|
| `recipeid` | int64 | Clé de jointure |
| `cluster_label` | str | Badge + filtre de cluster |

**`gold_recipe_ingredient_map.parquet`** (via `load_ingredient_map()`)

| Colonne | Type | Utilisé pour |
|---|---|---|
| `recipeid` | int64 | Clé de jointure |
| `matched_ingredients` | list[str] | Intersection du panier |
| `eufic_match_count` | int64 | Repli pour l'indicateur de saison 🟡 |
| `faostat_match_count` | int64 | (chargé, disponible) |

**`gold_sentiment_scores.parquet`** (via `load_sentiment()`)

| Colonne | Type | Utilisé pour |
|---|---|---|
| `recipeid` | int64 | Clé de jointure |
| `sentiment_percentile` | float64 | (chargé, disponible pour affichage futur) |

**`gold_recipe_durability_scores/durability_country=<X>/data.parquet`** (via `load_durability_scores(country)`, filtré sur `durability_month`)

| Colonne | Type | Utilisé pour |
|---|---|---|
| `recipeid` | int64 | Clé de jointure |
| `durability_month` | int64 | Filtre par mois sélectionné |
| `durability_score` | float64 | Badge durabilité + barre de progression |
| `coverage_score` | float64 | Affiché dans les détails de la recette |
| `seasonality_score` | float64 | Affiché dans les détails de la recette |
| `availability_score` | float64 | Affiché dans les détails de la recette |

**Parquets Silver** (données pays/panier, chargés en cache au démarrage)

| Fichier | Colonnes lues | Utilisé pour |
|---|---|---|
| `silver_seasonality_*.parquet` | `product_name`, `month_number`, `country`, `is_in_season` | Panier EUFIC |
| `silver_faostat_qcl_*.parquet` | `country_name`, `product_name`, `year`, `production_value` | Aliments de base FAOSTAT + liste de pays |

---

### 7. Instructions d'exécution

#### Prérequis

```bash
# From project root
pip install -r requirements.txt
```

Les parquets Gold requis doivent exister (exécuter d'abord le pipeline ML — voir `ml/README.md §9`).

#### Lancer l'application

```bash
streamlit run app/streamlit_app.py
```

S'ouvre sur **http://localhost:8501** (ou 8502 si 8501 est occupé par le FastAPI).

#### Lancer avec le FastAPI

```bash
# Terminal 1 — FastAPI
uvicorn api.main:app --reload                  # → http://127.0.0.1:8000

# Terminal 2 — Streamlit
streamlit run app/streamlit_app.py             # → http://localhost:8501
```

L'application Streamlit **n'appelle pas** le FastAPI en V1. Les deux peuvent tourner simultanément.

#### Comportement au démarrage à froid

Au premier clic sur le bouton, `build_merged()` charge et joint quatre parquets (~275K lignes au total) ; `load_durability_scores(country)` charge en parallèle la partition `durability_country=<pays>/data.parquet`. Cela prend 1–3 secondes au premier appel ; les appels suivants dans la même session sont instantanés (`@st.cache_data`).

Pour analyser le dataset de durabilité hors Streamlit : `python tools/analyze_durability_duckdb.py` (requêtes DuckDB sur les 29 partitions, exports CSV dans `reports/metrics/`).

---

### 8. Limitations connues & Feuille de route V2

#### Limitations V1

| Limitation | Impact |
|---|---|
| Lectures directes de parquets | Aucune journalisation des requêtes, aucune mise à l'échelle horizontale |
| FR/EN uniquement | Pas d'autres paramètres régionaux ; étiquettes de clusters toujours en anglais |
| Désaccord de vocabulaire du panier | La solution par sous-chaîne couvre la plupart des cas, mais les désaccords multi-mots (ex. : « sweet corn » vs « corn ») peuvent encore manquer |
| Aucune persistance de session utilisateur | Le panier et les filtres sont réinitialisés au rechargement de la page |
| `@st.cache_data` à portée de session | Plusieurs utilisateurs simultanés chargent chacun leur propre copie des 275K lignes |
| Cas limite préfixe inverse dans le filtre morphologique | Le token `"bel"` (ex. : issu de « Bel Paese cheese ») passe le garde morphologique de l'ingredient-matcher et se retrouve dans `matched_ingredients` comme `"bell pepper"`. Rare en pratique ; la correction V2 est un garde plus strict ou un NER au niveau des expressions (`ml/README.md §4.3`). |
| 4 ID de sentiment orphelins | Les IDs de recettes `{424301, 371545, 432898, 194165}` existent dans `gold_sentiment_scores` mais pas dans `gold_yummy_recommendations` (incohérence `reviewcount == 0` dans les sources). Jamais interrogés par l'interface. |
| `api/main.py` lit la partition durabilité à chaque requête | Aucun cache côté serveur. Gestion d'erreurs : 404 pour pays inconnu ou sans données, 500 si colonne manquante. La démo n'est pas affectée car l'interface lit les parquets directement. |
| Les scripts nécessitent une exécution depuis la racine du projet | Les chemins relatifs `Path("data/…")` utilisés partout — une exécution depuis un sous-répertoire déclenche une `FileNotFoundError`. |
| Stockage local, pas S3 runtime | L'API et Streamlit lisent `data/gold/` et `data/silver/` en local. MinIO est réservé au pipeline dbt de validation croisée (`s3://yummy/`). Migration vers S3/MinIO comme stockage runtime = V2, activable par config. |

#### Feuille de route V2

1. **Mode piloté par API** — remplacer les lectures directes de parquets par 5 nouveaux endpoints (voir §1) : `GET /basket-recommendations?basket=`, `GET /seasonal-products`, `GET /faostat-staples`, `GET /countries`, plus l'ajout de `cluster_label` et `matched_ingredients` au join interne. Gain : mise en cache côté serveur, déduplication des requêtes, observabilité.
2. **Traduction des noms de recettes** — noms d'affichage en français via l'API DeepL en batch (traduire une fois, mettre en cache dans un parquet).
3. **Panier enrichi** — afficher le contexte nutritionnel (calories, protéines) aux côtés du statut saisonnier ; nécessite la jointure d'un parquet nutritionnel supplémentaire.
4. **Persistance des préférences utilisateur** — `st.session_state` + stockage local du navigateur via `streamlit-js-eval` pour mémoriser le pays/la langue entre les sessions.
5. **Pagination** — afficher plus que le top 10 avec `st.pagination` (Streamlit ≥ 1.37).

---

### 9. API — couverture vérifiée (v1.2)

> **Cadrage.** L'API v1.2 expose **100 % des données** consommées par `build_merged()` (5 sources). Streamlit lit le Gold en direct **par choix de fluidité démo** (`@st.cache_data`, zéro réseau requis) ; le branchement UI→API est le premier chantier V2 (voir §1 et §8).

#### Matrice de couverture — 10/10 endpoints verts

| Endpoint | HTTP | Vérifié par |
|---|---|---|
| `GET /recommendations` | 200 | `cluster_label` + `matched_ingredients` présents dans le payload |
| `GET /basket-recommendations` (panier renseigné) | 200 | recettes matchées retournées |
| `GET /basket-recommendations` (panier vide) | 200 | fallback top-N déclenché |
| `GET /basket-recommendations` (pays inconnu) | 404 | 404 propre |
| `GET /seasonal-products` | 200 | `product_name` + `is_in_season` présents |
| `GET /seasonal-products` (pays inconnu) | 404 | 404 propre |
| `GET /faostat-staples` | 200 | `production_value` présent, ≤ top\_n lignes |
| `GET /faostat-staples` (pays inconnu) | 404 | 404 propre |
| `GET /countries` | 200 | 248 entrées, booleans `eufic`/`faostat` typés |
| `GET /health` (champs v1.2) | 200 | 4 nouveaux champs de santé présents |

Preuve reproductible : `python tools/prove_api_coverage.py` (depuis la racine du projet).

#### Parité logique API ≡ Streamlit

| Point | Résultat |
|---|---|
| **Basket France/Juin, panier `['apricot','artichoke','aubergine']`** | API = 3 711 recettes, Streamlit = 3 711 — **identiques** |
| **`_ingredient_hits`** | Substring bidirectionnel (`b in i or i in b`) copié verbatim depuis `streamlit_app.py` |
| **`_FAO_AGGREGATE_PATTERNS`** | Tuple identique : `("primary", " total", ", total", "poultry", " meat", "equivalent", "oilcrop")` — 0 agrégat dans le top |
| **`GET /countries`** | 29 🟢 (EUFIC) + 219 🟡 (FAOSTAT uniquement) = 248 — correspond exactement au bandeau de confiance Streamlit |

#### Nuances assumées (choix de conception, pas des écarts)

**a) Fallback panier**

Streamlit implémente 3 niveaux :
1. Intersection panier × `matched_ingredients`
2. Si vide : nouvelle tentative avec le panier saisonnier complet (fallback saisonnier)
3. Si toujours vide : top-N global

L'API collapse les niveaux 2 et 3 en un unique fallback top-N global. Sans impact sur les paniers avec résultats (cas normal) ; **simplification API assumée**, documentée ici pour traçabilité.

**b) Casse des clés pays**

L'API retourne les clés internes minuscules (`"czechrepublic"`, `"france"`) — ce sont les valeurs à passer aux autres endpoints. Streamlit utilise des display names en casse titre (`"Czech Republic"`, `"France"`) pour l'affichage UI. **Équivalence logique**, différence de présentation uniquement. Un mapping display↔interne (via `EUFIC_DISPLAY_MAP`) resterait à ajouter si l'UI consommait l'API directement (chantier V2).

---
---

## 🇬🇧 English version

# YUMMY Streamlit UI — Technical Documentation

> **Figures from canonical run dated 2026-05-28** (see `ml/README.md` for pipeline details).

> **File:** `app/streamlit_app.py`  
> **Run:** `streamlit run app/streamlit_app.py`  
> **Default port:** 8501 (auto-increments if occupied)

---

## 1. Overview

The YUMMY UI is a single-page Streamlit application that recommends recipes
personalised to a user's country, the current month, and a selected basket
of seasonal ingredients.

**Why direct parquet reads (not FastAPI) for the demo:**

| Concern | Demo choice | V2 choice |
|---|---|---|
| Latency | `@st.cache_data` loads parquets once per session (~2 s cold start, <1 ms cached) | FastAPI serves pre-loaded data with HTTP caching headers |
| Deployment simplicity | Single `streamlit run` command, no separate API process | Two processes + load balancer |
| Offline demo | Works without network | Requires running API |
| Observability | None | API middleware for request logging, latency tracking |

The FastAPI (`api/main.py`) exists and exposes `GET /recommendations`, enriched with durability scores (country × month) since Sarah's commit. It covers 2 of the 5 sources aggregated by `build_merged()`: recommendations and durability. The remaining 3 sources (clusters, ingredient map, seasonal basket) are read directly by Streamlit.
`app/streamlit_app.py` is intentionally decoupled for demo stability.

**V2 migration path (5 workstreams, not a drop-in):** fully serving the app through the API requires:
1. `GET /basket-recommendations?country=&month=&basket=` — filters on `matched_ingredients`, returns `cluster_label` and `matched_ingredients` in the payload;
2. `GET /seasonal-products?country=&month=` — EUFIC in-season products (currently read from Silver);
3. `GET /faostat-staples?country=` — FAOSTAT staples (currently read from Silver);
4. `GET /countries` — list of available countries (EUFIC ∪ FAOSTAT);
5. Add `cluster_label` and `matched_ingredients` to the API's internal join.

The basket logic (EUFIC×month intersection, FAOSTAT staples, confidence banner) currently lives entirely in Streamlit.

---

## 2. User Journey (Parcours utilisateur)

```
┌─────────────────────────────────────────────────────────────────┐
│  Step 1 — Language                                               │
│  Select 🇫🇷 Français or 🇬🇧 English (sidebar (left))            │
│  All UI strings switch immediately; ML cluster labels stay EN.   │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 2 — Context                                                │
│  Pick Country (273 options) + Month (Jan–Dec, default June).     │
│  A confidence banner appears immediately below showing whether   │
│  EUFIC 🟢, FAOSTAT 🟡, or neither 🔴 has data for that country. │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 3 — Ingredient basket                                      │
│  Multiselect pre-populated with up to 3 items from:             │
│   - EUFIC in-season products (country × month) → 🟢 items       │
│   - FAOSTAT top-produced staples (latest year) → 🟡 items       │
│  User can add, remove, or keep defaults.                         │
│  Always pre-selected (never empty) — see §3.3.                   │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 4 — Cluster filter (optional)                              │
│  Multiselect with all 5 cluster labels checked by default.       │
│  Deselect any cluster to narrow results to recipe type.          │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 5 — Generate                                               │
│  Click "🍽️ Generate Recommendations" (full-width primary button)│
│  If basket is empty → warning, no results shown.                 │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 6 — Post-generation filters                               │
│  Slider "⏱️ Max time": 10–180 min (default 60, step 5).        │
│  Radio "Sort by": Score Yummy · Score Durabilité ·              │
│  Best trade-off (0.6 × Yummy + 0.4 × Durability).              │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 7 — Results overview                                      │
│  4 aggregate metrics: recipe count · avg Yummy Score ·          │
│  avg Durability Score · avg prep time.                          │
│  + 2 "Understand the Score" expanders (Yummy / Durability).     │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 8 — Recipe cards                                          │
│  Top 10 in the chosen sort order. Each card: name, category,    │
│  medal 🥇/🥈/🥉 (ranks 1–3), Yummy Score + bar,               │
│  Durability + badge (🌱/🌿/🟡/🔴) + bar, rating, time,        │
│  cluster badge, season flag 🟢/🟡, caption.                    │
│  Expander "📖 Recipe details": seasonality, agricultural        │
│  availability, coverage (/100) + recognised ingredients.        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Functional Features

### 3.1 Confidence banner

Immediately after country/month selection, a pill-shaped banner appears:

| Condition | Colour | Message |
|---|---|---|
| Country in EUFIC | 🟢 green tint | "Reliable seasonal data (EUFIC)" |
| Country in FAOSTAT only | 🟡 amber tint | "Agricultural availability proxy (FAOSTAT)" |
| Neither | 🔴 red tint | "Limited data — low confidence" |

EUFIC covers 29 European countries; FAOSTAT covers 244 countries/regions.

### 3.2 Seasonal basket enrichment

The basket combines two sources to ensure even non-EUFIC countries have
pre-selected ingredients:

```python
eufic_items  = get_seasonal_products(country, month)  # EUFIC in-season
faostat_only = [p for p in get_faostat_staples(country)
                if p not in set(eufic_items)]          # FAOSTAT, deduped
all_options  = eufic_items + faostat_only
```

FAOSTAT aggregate categories ("vegetables primary", "meat, total", etc.)
are excluded by keyword filter before presenting to the user.

### 3.3 Default selection behaviour

```python
default_basket = all_options[:3]   # always the first 3 available items
```

This guarantees the multiselect is never empty on initial render,
even for countries with no EUFIC data (e.g., Gabon shows FAOSTAT staples).
The user must manually clear the selection to trigger the "no ingredients"
warning.

### 3.4 Cluster filter

All 5 clusters are selected by default (no filtering).
If the user deselects clusters and the intersection with basket results
is empty, the cluster filter is silently ignored and the basket results
are shown unchanged, with an info message explaining the fallback.

### 3.5 FR/EN language toggle

i18n is implemented as a plain Python dict:

```python
TEXTS = {
    "fr": { "title": "🍽️ YUMMY", "btn_generate": "🍽️ Générer…", … },
    "en": { "title": "🍽️ YUMMY", "btn_generate": "🍽️ Generate…", … },
}
lang = st.selectbox(…)   # "fr" or "en"
texts = TEXTS[lang]      # all subsequent UI strings use texts["key"]
```

**Why not gettext / GNU i18n:**  
The app has ~35 translatable strings, all hardcoded in one file.
gettext adds build-step complexity (`.po` / `.mo` files, extraction tooling)
with no benefit at this scale. A plain dict is transparent, version-controlled,
and refactored in seconds.

**Cluster labels are intentionally not translated.** They are the ML taxonomy
output (`cluster_label` column in Gold parquets) and serve as an interface
contract between the ML and UI layers — translating them would break that
contract and require re-labelling the parquets.

### 3.6 Preparation time filter

After generation, a slider lets the user restrict results by prep time:

```python
max_time = st.slider("⏱️ Temps maximum de préparation", min_value=10, max_value=180, value=60, step=5)
cluster_results = cluster_results[cluster_results["totaltime"].fillna(999) <= max_time]
```

Recipes with `NaN` totaltime are treated as 999 min and filtered out once the
slider falls below 999. The filter is applied before sorting.

### 3.7 Results sort mode

A horizontal radio with three options appears below the slider:

| Option | Behaviour |
|---|---|
| **Score Yummy** | `sort_values("yummy_score", ascending=False)` |
| **Score Durabilité** | `sort_values("durability_score", ascending=False)` |
| **Meilleur compromis** | `0.6 × yummy_score + 0.4 × durability_score`, sorted descending |

> **Note:** the "Score Durabilité" and "Meilleur compromis" sorts rely on `durability_score`
> loaded from the `durability_country=<country>` partition for the selected month — the score
> reflects the user's actual country and month selection (see `ml/README.md §7.4`).

### 3.8 Results overview

Shown after sorting, before the recipe cards:

```python
st.subheader("📊 Aperçu des résultats")
# 4 columns: recipe count · avg Yummy Score · avg Durability Score · avg prep time
```

Followed by two expanders:
- **Comprendre le Score Yummy** — component breakdown (rating, popularity, simplicity, sentiment).
- **🌍 Comprendre le Score de Durabilité** — formula (75 % seasonality + 25 % availability, bonus ≥ 2/3).

### 3.9 Recipe details expander

Each recipe card has an expander `📖 Détails de la recette` that exposes:

- 🌱 **Seasonality**: `seasonality_score / 100`
- 🌾 **Agricultural availability**: `availability_score / 100`
- 🎯 **Coverage**: `coverage_score / 100`
- 🧺 List of recognised ingredients (`matched_ingredients`)

---

## 4. Recommendation Logic (Logique de recommandation)

### 4.1 Basket → recipe intersection

```python
def _ingredient_hits(ingredients: set[str], basket_set: set[str]) -> set[str]:
    hits = set()
    for b in basket_set:
        for i in ingredients:
            if b in i or i in b:    # bidirectional substring match
                hits.add(b)
                break
    return hits
```

**Why substring (not exact) matching:**  
The Gold `matched_ingredients` column stores TF-IDF-matched reference terms,
which may differ lexically from EUFIC basket items:

| EUFIC basket item | `matched_ingredients` value | Exact match? | Substring? |
|---|---|---|---|
| `"aubergine"` | `"eggplants (aubergines)"` | ✗ | ✓ |
| `"tomato"` | `"tomato"` | ✓ | ✓ |
| `"garlic"` | `"garlic"` | ✓ | ✓ |

### 4.2 Ranking

Qualifying recipes are sorted descending by `yummy_score` and the top 10 returned.
`yummy_score` is a Bayesian-adjusted composite (see `ml/README.md §6` for formula).

**Concrete example — France, July, basket = `['apricot', 'artichoke', 'aubergine']`:**
- **3,711** recipes qualify (substring match against `matched_ingredients`)
- \#1 result: *Caponata Eggplant And Lots Of Good Things* — WR 4.834, 9 reviews,
  shrunk sentiment 76.96, yummy\_score **72.64**
- All top-10 results have 6–23 reviews and WR ≥ 4.79 — no low-review outliers
  (canonical run 2026-05-28; full table in `ml/README.md §5.4`)

### 4.3 Explainability line

Each card shows one plain-text caption naming the actual matched ingredients:

```
"Recommended because: popular (9 reviews), ready in 25 min, matches: aubergine, artichoke."
```

Components shown only when non-zero:
- `popular (N reviews)` — from `reviewcount`
- `ready in T min` — from `totaltime`
- `matches: X, Y` — intersection of user's basket with `matched_ingredients`

### 4.4 Fallback tiers

```
Tier 1 (normal):    basket_set ∩ matched_ingredients  →  results
                              ↓ empty
Tier 2 (selection fallback):  all_options ∩ matched_ingredients  →  results
                              + info: "No recipe matches your exact selection"
                              ↓ empty
Tier 3 (global fallback):     global top-N sorted by yummy_score
                              + info: "No recipes found matching your basket"
```

In Tier 2, the explainability line is replaced with an honest message
("no selection — top seasonal picks") rather than inventing ingredient matches
that don't correspond to the user's actual selection.

---

## 5. UI/UX Design

### 5.1 Theme — `.streamlit/config.toml`

```toml
[theme]
primaryColor             = "#F4A261"   # warm amber (spice/curry tone)
backgroundColor          = "#111118"   # near-black, warm dark base
secondaryBackgroundColor = "#1A1A22"   # card backgrounds
textColor                = "#E8E8E3"   # warm off-white
font                     = "sans serif"
```

Poppins (Google Fonts, 400/500/600/700) is loaded via injected CSS and
overrides the `font = "sans serif"` fallback for all visible text.

### 5.2 CSS injection approach

```python
def inject_css() -> None:
    st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)
```

`inject_css()` is called once at the start of `main()`. The `<style>` block
is appended to the Streamlit page's `<head>` and scopes globally.

**Version-coupling risk:** Streamlit's HTML structure (CSS class names like
`.block-container`, data-testid attributes) can change across minor versions.
The CSS uses a mix of stable semantic selectors (`.main .block-container`)
and data-testid selectors for widget-level tweaks. If Streamlit updates
break a selector, only that widget's styling is affected — layout and logic
remain intact. Pinning Streamlit version in `requirements.txt` mitigates this.

### 5.3 Card design

Recipe cards are rendered as injected HTML via `st.markdown(unsafe_allow_html=True)`:

```
┌──────────────────────────────────────────────── 🟢 ─┐
│  Recipe Name (bold, 1.05rem)                          │
│  [category tag]                                       │
│─────────────────────────────────────────────────────│
│  YUMMY SCORE │ RATING  │ TIME    │ CLUSTER           │
│  72.6/100    │ 4.8/5   │ 25 min  │ [⚡ Quick & Easy] │
│  ████████░░░                                          │  ← gradient progress bar
│─────────────────────────────────────────────────────│
│  Recommended because: popular (9 reviews),            │
│  ready in 25 min, matches: aubergine.                 │
└──────────────────────────────────────────────────────┘
```

- Hover: `transform: translateY(-2px)` + stronger shadow — CSS-only, zero JS
- Progress bar: `width: {yummy}%` inline style capped at 100

**Cluster badge colours:**

| Cluster | Badge class | Colour |
|---|---|---|
| 🏆 Top Rated | `badge-top` | Amber `#FCD34D` on tinted bg |
| ⭐ Crowd Favourite | `badge-crowd` | Blue `#93C5FD` |
| ⚡ Quick & Easy | `badge-quick` | Green `#6EE7B7` |
| 🌿 Seasonal & Local | `badge-seasonal` | Teal `#5EEAD4` |
| 🌍 Global Kitchen | `badge-global` | Purple `#C4B5FD` |

### 5.4 Why native Streamlit over third-party component libraries

| Concern | Decision |
|---|---|
| Dependency risk | Third-party Streamlit components depend on React versions and may break on Streamlit upgrades |
| Build complexity | Custom components require Node.js build toolchain |
| Offline demo | External CDN components fail without network |
| Sufficient control | CSS injection + `unsafe_allow_html` on `st.markdown` provides full card-level design control |

All interactive widgets (multiselect, selectbox, button, spinner, expander)
remain native Streamlit. Only display-only elements use injected HTML.

---

## 6. Data Contracts (Contrats de données)

The columns listed here are the **interface between the ML pipeline and the UI**.
Changes to column names or types in Gold parquets must be reflected here.

### Loaded by `app/streamlit_app.py`

**`gold_yummy_recommendations.parquet`** (via `load_recommendations()`)

| Column | Type | Used for |
|---|---|---|
| `recipeid` | int64 | Join key |
| `name` | str | Card title |
| `recipecategory` | str | Card category tag |
| `totaltime` | int64 | "Time" metric, explainability |
| `aggregatedrating` | float64 | "Rating" metric |
| `reviewcount` | float64 | Explainability line |
| `yummy_score` | float64 | Ranking + progress bar |

**`gold_recipe_clusters.parquet`** (via `load_clusters()`)

| Column | Type | Used for |
|---|---|---|
| `recipeid` | int64 | Join key |
| `cluster_label` | str | Badge + cluster filter |

**`gold_recipe_ingredient_map.parquet`** (via `load_ingredient_map()`)

| Column | Type | Used for |
|---|---|---|
| `recipeid` | int64 | Join key |
| `matched_ingredients` | list[str] | Basket intersection |
| `eufic_match_count` | int64 | 🟡 season flag fallback |
| `faostat_match_count` | int64 | (loaded, available) |

**`gold_sentiment_scores.parquet`** (via `load_sentiment()`)

| Column | Type | Used for |
|---|---|---|
| `recipeid` | int64 | Join key |
| `sentiment_percentile` | float64 | (loaded, available for future display) |

**`gold_recipe_durability_scores/durability_country=<X>/data.parquet`** (via `load_durability_scores(country)`, filtered on `durability_month`)

| Column | Type | Used for |
|---|---|---|
| `recipeid` | int64 | Join key |
| `durability_month` | int64 | Filter by selected month |
| `durability_score` | float64 | Durability badge + progress bar |
| `coverage_score` | float64 | Displayed in recipe details |
| `seasonality_score` | float64 | Displayed in recipe details |
| `availability_score` | float64 | Displayed in recipe details |

**Silver parquets** (country/basket data, loaded cached at startup)

| File | Columns read | Used for |
|---|---|---|
| `silver_seasonality_*.parquet` | `product_name`, `month_number`, `country`, `is_in_season` | EUFIC basket |
| `silver_faostat_qcl_*.parquet` | `country_name`, `product_name`, `year`, `production_value` | FAOSTAT staples + country list |

---

## 7. Run Instructions

### Prerequisites

```bash
# From project root
pip install -r requirements.txt
```

Required Gold parquets must exist (run the ML pipeline first — see `ml/README.md §9`).

### Start the app

```bash
streamlit run app/streamlit_app.py
```

Opens at **http://localhost:8501** (or 8502 if 8501 is occupied by the FastAPI).

### Run alongside the FastAPI

```bash
# Terminal 1 — FastAPI
uvicorn api.main:app --reload                  # → http://127.0.0.1:8000

# Terminal 2 — Streamlit
streamlit run app/streamlit_app.py             # → http://localhost:8501
```

The Streamlit app does **not** call the FastAPI in V1. Both can run simultaneously.

### Cold start behaviour

On first button click, `build_merged()` loads and joins four parquets
(~275K rows total); `load_durability_scores(country)` loads the
`durability_country=<country>/data.parquet` partition in parallel.
This takes 1–3 seconds on first call; subsequent calls within the
same session are instant (`@st.cache_data`).

For analytical queries on the durability dataset outside Streamlit:
`python tools/analyze_durability_duckdb.py` (DuckDB queries across all
29 partitions, CSV exports to `reports/metrics/`).

---

## 8. Known Limitations & V2 Roadmap

### V1 limitations

| Limitation | Impact |
|---|---|
| Direct parquet reads | No request logging, no horizontal scaling |
| FR/EN only | No other locales; cluster labels always English |
| Basket vocabulary mismatch | Substring workaround handles most cases, but multi-word mismatches (e.g., "sweet corn" vs "corn") may still miss |
| No user session persistence | Basket and filters reset on page reload |
| `@st.cache_data` session-scoped | Multiple concurrent users each load their own copy of 275K rows |
| `"bel"` → `"bell pepper"` reverse-prefix edge case | Token `"bel"` (e.g., from "Bel Paese cheese") passes the ingredient-matcher morphological guard and lands in `matched_ingredients` as `"bell pepper"`. Rare in practice; V2 fix is tighter guard or phrase-level NER (`ml/README.md §4.3`). |
| 4 orphan sentiment IDs | Recipe IDs `{424301, 371545, 432898, 194165}` exist in `gold_sentiment_scores` but not in `gold_yummy_recommendations` (source `reviewcount == 0` inconsistency). They are never queried by the UI. |
| `api/main.py` reads durability partition per request | No server-side cache. Error handling: 404 for unknown country or no data, 500 for missing column. Demo is unaffected because the UI reads parquets directly. |
| Scripts require project-root execution | Relative `Path("data/…")` paths used throughout — running from a subdirectory raises `FileNotFoundError`. |
| Local storage, no S3 runtime | API and Streamlit read `data/gold/` and `data/silver/` from the local filesystem. MinIO is reserved for the dbt cross-validation pipeline (`s3://yummy/`). Migrating to S3/MinIO as the runtime store is a V2 goal, activatable by configuration. |

### V2 roadmap

1. **API-driven mode** — replace direct parquet reads with 5 new endpoints (see §1): `GET /basket-recommendations?basket=`, `GET /seasonal-products`, `GET /faostat-staples`, `GET /countries`, plus adding `cluster_label` and `matched_ingredients` to the API's internal join. Gain: server-side caching, request deduplication, observability.
2. **Recipe name translation** — French display names via DeepL API batch
   (translate once, cache in parquet).
3. **Richer basket** — show nutrient context (calories, protein) alongside
   seasonal status; requires joining an additional nutrition parquet.
4. **User preference persistence** — `st.session_state` + browser local storage
   via `streamlit-js-eval` to remember country/language across sessions.
5. **Pagination** — show more than top 10 with `st.pagination` (Streamlit ≥ 1.37).

---

## 9. API — Verified Coverage (v1.2)

> **Framing.** The API v1.2 exposes **100% of the data** consumed by `build_merged()` (5 sources). Streamlit reads Gold parquets directly **by demo-fluency choice** (`@st.cache_data`, no network required); wiring the UI to the API is the first V2 workstream (see §1 and §8).

### Coverage matrix — 10/10 endpoints green

| Endpoint | HTTP | Verified by |
|---|---|---|
| `GET /recommendations` | 200 | `cluster_label` + `matched_ingredients` present in payload |
| `GET /basket-recommendations` (basket supplied) | 200 | matched recipes returned |
| `GET /basket-recommendations` (empty basket) | 200 | global top-N fallback triggered |
| `GET /basket-recommendations` (unknown country) | 404 | clean 404 |
| `GET /seasonal-products` | 200 | `product_name` + `is_in_season` present |
| `GET /seasonal-products` (unknown country) | 404 | clean 404 |
| `GET /faostat-staples` | 200 | `production_value` present, ≤ top\_n rows |
| `GET /faostat-staples` (unknown country) | 404 | clean 404 |
| `GET /countries` | 200 | 248 entries, `eufic`/`faostat` typed booleans |
| `GET /health` (v1.2 fields) | 200 | 4 new health fields present |

Reproducible proof: `python tools/prove_api_coverage.py` (from project root).

### Logic parity API ≡ Streamlit

| Point | Result |
|---|---|
| **Basket France/June, basket `['apricot','artichoke','aubergine']`** | API = 3,711 recipes, Streamlit = 3,711 — **identical** |
| **`_ingredient_hits`** | Bidirectional substring (`b in i or i in b`) copied verbatim from `streamlit_app.py` |
| **`_FAO_AGGREGATE_PATTERNS`** | Identical tuple: `("primary", " total", ", total", "poultry", " meat", "equivalent", "oilcrop")` — 0 aggregate in top results |
| **`GET /countries`** | 29 🟢 (EUFIC) + 219 🟡 (FAOSTAT-only) = 248 — matches the Streamlit confidence banner exactly |

### Deliberate design choices (not gaps)

**a) Basket fallback tiers**

Streamlit implements 3 fallback tiers:
1. Basket ∩ `matched_ingredients`
2. If empty: retry with full seasonal product set (seasonal fallback)
3. If still empty: global top-N

The API collapses tiers 2 and 3 into a single global top-N fallback. No impact for baskets that return results (the normal case); **deliberate API simplification**, documented here for traceability.

**b) Country key casing**

The API returns lowercase internal keys (`"czechrepublic"`, `"france"`) — these are the values to pass to other endpoints. Streamlit uses title-cased display names (`"Czech Republic"`, `"France"`) for UI rendering. **Logically equivalent**, presentation difference only. A display↔internal mapping (via `EUFIC_DISPLAY_MAP`) would need to be added if the UI consumed the API directly (V2 workstream).

---
---