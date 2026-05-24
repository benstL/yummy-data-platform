# Yummy Data Platform — Couche de transformation (Silver / Gold)

Transformation des données du **Yummy Score** (recommandation de recettes durables)
avec **dbt** sur moteur **DuckDB**, lisant la couche Bronze depuis **MinIO** (S3).

Cette couche applique le pattern **Medallion** : elle nettoie les données brutes
(Bronze → Silver), puis les assemble en un score exploitable (Silver → Gold).

---

## 1. État actuel

**Couche staging (Silver) — terminée.** 7 modèles, 20 tests, couvrant les 4 piliers :

| Modèle | Pilier Yummy Score | Source |
|---|---|---|
| `stg_ciqual` | Nutrition | CIQUAL (ANSES) |
| `stg_agribalyse` | Empreinte carbone | Agribalyse (ADEME) |
| `stg_eufic` | Saisonnalité | EUFIC |
| `stg_interactions` | Satisfaction | Kaggle Food.com (avis) |
| `stg_recipes` | Catalogue recettes | Kaggle Food.com |
| `stg_recipes_web` | Catalogue recettes (FR) | Marmiton / 750g |
| `stg_faostat` | Carbone (proxy secondaire) | FAOSTAT (FAO) |

**À construire** : les modèles `intermediate/` (jointures entre piliers) et
`marts/` (le Yummy Score final).

---

## 2. Prérequis

- Le projet racine doit être installé : `pip install -e .` (depuis la racine du dépôt).
- **MinIO** doit tourner (`docker compose up -d minio` depuis la racine).
- Le fichier `.env` de la racine doit contenir les credentials MinIO
  (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `MINIO_ENDPOINT`). dbt les lit via
  `env_var()`.
- dbt et l'adaptateur DuckDB installés (`dbt-duckdb`).

---

## 3. Configuration

La connexion est définie dans `profiles.yml` : moteur **DuckDB** (base locale
`yummy.duckdb`), avec l'extension `httpfs` pour lire le Bronze directement sur MinIO
en S3. Le réglage clé est `s3_use_ssl: false` (MinIO local tourne en HTTP).

Les sources Bronze sont déclarées dans `models/staging/sources.yml` : chaque table
pointe vers un fichier MinIO via `read_csv_auto('s3://bronze/...')` (ou `read_json`
pour les recettes web).

Vérifier que tout est branché :

```bash
dbt debug        # doit afficher "All checks passed!"
```

---

## 4. Utilisation

Toutes les commandes se lancent depuis ce dossier (`transform/yummy_dbt/`), MinIO
démarré, le venv activé.

```bash
# Construire tous les modèles staging
dbt run --select staging

# Construire un seul modèle
dbt run --select stg_ciqual

# Lancer les tests (contrats : clés uniques, non nulles, valeurs valides)
dbt test --select staging

# Tout construire puis tester (build = run + test)
dbt build

# Vérifier la config sans rien exécuter
dbt parse
```

Inspecter un résultat :

```bash
python3 -c "import duckdb; c=duckdb.connect('yummy.duckdb'); \
print(c.execute('SELECT * FROM stg_ciqual LIMIT 5').df())"
```

---

## 5. Règles et conventions

Ces règles garantissent que tous les modèles se comportent pareil et restent
interchangeables entre membres de l'équipe.

### 5.1 Les trois niveaux
- **`staging/` (`stg_*`)** — nettoie UNE source. Lit une `source()`, jamais un autre
  modèle. Renommage, casting, normalisation.
- **`intermediate/` (`int_*`)** — croise plusieurs stagings (jointures, calculs).
  Lit des `ref()`, jamais une `source()`.
- **`marts/`** — tables finales (le Yummy Score), servies à l'API. Lit des `int_`.

Règle d'or : un `stg_` lit une `source()`, un `int_`/`mart_` lit des `ref()`.

### 5.2 Frontière Bronze / Silver
Bronze = donnée brute. Toute transformation métier (renommage de colonnes, filtrage,
calcul) se fait **ici, en Silver**, jamais à l'extraction. Le staging convertit et
nettoie ; il ne réinvente pas la donnée.

### 5.3 Anatomie d'un modèle staging
```sql
WITH source AS (
    SELECT * FROM {{ source('minio_bronze', 'raw_<source>') }}
),
renamed AS (
    SELECT <colonne_brute> AS <nom_clair_snake_case>, ...
    FROM source
)
SELECT * FROM renamed
WHERE <garde-fou : clé NOT NULL, valeur dans la plage attendue>
```

Conventions :
- Noms de sortie en **snake_case anglais** (`energy_kcal_100g`).
- Une **clé** explicite par table (`ingredient_id`, `recipe_id`...).
- Toujours un **`WHERE` de garde-fou** final.
- Documenter chaque modèle dans `schema.yml` (description + tests).

### 5.4 Choisir la technique de nettoyage
Regarder d'abord le type détecté par DuckDB (`DESCRIBE SELECT ...`) :

| Cas | Symptôme | Technique | Exemple |
|---|---|---|---|
| Source sale | virgules FR (`"4,41"`), `< 0,2`, `-` | macro `ciqual_num()` | `stg_ciqual` |
| Source propre | déjà typée DOUBLE/BIGINT | `TRY_CAST(col AS ...)` | `stg_agribalyse` |
| À normaliser | texte à mapper (mois) | `CASE WHEN ...` | `stg_eufic` |
| Listes encodées | `"['a','b']"` | `string_split(...)` | `stg_recipes` |
| JSON imbriqué | enveloppe + liste | `UNNEST(recipes)` | `stg_recipes_web` |

La macro `ciqual_num()` (dans `macros/`) gère virgule FR + `< X` + `-` + `traces`.
Ne pas la copier : l'appeler. Si un cas manque, étendre la macro (et prévenir l'équipe).

### 5.5 Configuration centralisée
La matérialisation est définie par dossier dans `dbt_project.yml`
(`staging: +materialized: table`), pas par `{{ config() }}` dans chaque fichier.
Le `{{ config() }}` local est réservé aux exceptions (un modèle qui déroge à son dossier).

### 5.6 Clés de jointure connues
- `stg_ciqual.ingredient_id` ↔ `stg_agribalyse.ciqual_code` (INTEGER, 94% de recouvrement).
- `stg_interactions.recipe_id` ↔ `stg_recipes.recipe_id` (BIGINT).
- ⚠️ EUFIC ↔ CIQUAL : pas de clé code. Jointure par nom (anglais ↔ français), à
  traiter avec soin en intermediate.

---

## 6. Structure

```
transform/yummy_dbt/
├── dbt_project.yml          # config projet + matérialisations par couche
├── profiles.yml             # connexion DuckDB + accès MinIO (S3)
├── macros/
│   └── ciqual_num.sql       # nettoyage virgules FR / valeurs censurées
└── models/
    ├── staging/             # stg_* : nettoyage par source (FAIT)
    │   ├── sources.yml      # déclaration des 7 sources Bronze
    │   ├── schema.yml       # doc + tests des modèles
    │   └── stg_*.sql        # les 7 modèles staging
    ├── intermediate/        # int_* : jointures entre piliers (À FAIRE)
    └── marts/               # le Yummy Score final (À FAIRE)
```

---

## 7. Points de vigilance

- **Décimales françaises** : CIQUAL utilise la virgule → colonne lue en texte →
  macro `ciqual_num`.
- **Valeurs censurées** (`< 0,2`, `-`, `traces`) : choix retenu = `< X` devient X,
  `-`/`traces` deviennent NULL. Choix métier, impacte le Nutri-Score.
- **Langue** : Kaggle = anglais, Marmiton = français. Catalogues à unifier avec soin
  (clés de types différents : BIGINT vs slug texte).
- **FAOSTAT** : fichier mondial énorme, filtré dès le staging (France, Production,
  années ≥ 2018) et dédoublonné sur la dernière extraction.
