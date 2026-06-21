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

Le FastAPI (`api/main.py`) existe et expose `GET /recommendations`.
`app/streamlit_app.py` est intentionnellement découplé pour la stabilité de la démo.
Le chemin de migration V2 consiste à remplacer l'appel `build_merged()` par une requête API — aucune autre modification requise.

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
│  Step 6 — Results                                                │
│  Top 10 recipe cards, ranked by yummy_score.                     │
│  Each card shows: name, category, Yummy Score (+ progress bar),  │
│  Rating, Time, Cluster badge (colour-coded), season flag 🟢/🟡,  │
│  and an explainability caption.                                  │
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

**`gold_recipe_durability_scores.parquet`** (via `load_recommendations()`)

| Colonne | Type | Utilisé pour |
|---|---|---|
| `durability_score` | float64 | Badge durabilité + barre de progression |
| `coverage_score` | float64 | (chargé, disponible) |
| `seasonality_score` | float64 | (chargé, disponible) |
| `availability_score` | float64 | (chargé, disponible) |

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

Au premier clic sur le bouton, `build_merged()` charge et joint quatre parquets (~275K lignes au total). Cela prend 1–3 secondes au premier appel ; les appels suivants dans la même session sont instantanés (`@st.cache_data`).

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
| `api/main.py` lit le parquet à chaque requête | Aucun cache côté serveur ni gestion d'erreur pour un fichier manquant. Pris en charge par l'équipe API ; signalé à leur backlog. La démo n'est pas affectée car l'interface lit les parquets directement. |
| Les scripts nécessitent une exécution depuis la racine du projet | Les chemins relatifs `Path("data/…")` utilisés partout — une exécution depuis un sous-répertoire déclenche une `FileNotFoundError`. |
| Score de durabilité pré-calculé pour France / Juin uniquement | La sélection pays/mois pilote le panier d'ingrédients EUFIC, mais ne recalcule pas le `durability_score` affiché — celui-ci reste celui de France / Juin quelle que soit la sélection (voir `ml/README.md §7.4`). |

#### Feuille de route V2

1. **Mode piloté par API** — remplacer `build_merged()` par `GET /recommendations?basket=…` pour ajouter la mise en cache côté serveur, la déduplication des requêtes et l'observabilité.
2. **Traduction des noms de recettes** — noms d'affichage en français via l'API DeepL en batch (traduire une fois, mettre en cache dans un parquet).
3. **Panier enrichi** — afficher le contexte nutritionnel (calories, protéines) aux côtés du statut saisonnier ; nécessite la jointure d'un parquet nutritionnel supplémentaire.
4. **Persistance des préférences utilisateur** — `st.session_state` + stockage local du navigateur via `streamlit-js-eval` pour mémoriser le pays/la langue entre les sessions.
5. **Pagination** — afficher plus que le top 10 avec `st.pagination` (Streamlit ≥ 1.37).

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

The FastAPI (`api/main.py`) exists and exposes `GET /recommendations`.
`app/streamlit_app.py` is intentionally decoupled for demo stability.
The V2 migration path is to replace the `build_merged()` call with an
API fetch — no other changes required.

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
│  Step 6 — Results                                                │
│  Top 10 recipe cards, ranked by yummy_score.                     │
│  Each card shows: name, category, Yummy Score (+ progress bar),  │
│  Rating, Time, Cluster badge (colour-coded), season flag 🟢/🟡,  │
│  and an explainability caption.                                  │
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

**`gold_recipe_durability_scores.parquet`** (via `load_recommendations()`)

| Column | Type | Used for |
|---|---|---|
| `durability_score` | float64 | Durability badge + progress bar |
| `coverage_score` | float64 | (loaded, available) |
| `seasonality_score` | float64 | (loaded, available) |
| `availability_score` | float64 | (loaded, available) |

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
(~275K rows total). This takes 1–3 seconds on first call; subsequent
calls within the same session are instant (`@st.cache_data`).

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
| `api/main.py` reads parquet per request | No server-side cache or graceful error handling for a missing file. Owned by the API team; flagged for their backlog. Demo is unaffected because the UI reads parquets directly. |
| Scripts require project-root execution | Relative `Path("data/…")` paths used throughout — running from a subdirectory raises `FileNotFoundError`. |
| Durability score pre-computed for France / June only | The country/month selection drives the EUFIC ingredient basket but does not recompute the displayed `durability_score` — it stays France / June regardless of selection (see `ml/README.md §7.4`). |

### V2 roadmap

1. **API-driven mode** — replace `build_merged()` with `GET /recommendations?basket=…`
   to add server-side caching, request deduplication, and observability.
2. **Recipe name translation** — French display names via DeepL API batch
   (translate once, cache in parquet).
3. **Richer basket** — show nutrient context (calories, protein) alongside
   seasonal status; requires joining an additional nutrition parquet.
4. **User preference persistence** — `st.session_state` + browser local storage
   via `streamlit-js-eval` to remember country/language across sessions.
5. **Pagination** — show more than top 10 with `st.pagination` (Streamlit ≥ 1.37).

---
---