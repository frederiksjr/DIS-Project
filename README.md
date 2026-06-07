# CineMatch — Movie Recommender

A Flask web application that recommends movies using a KNN (K-Nearest Neighbours)
algorithm backed by a PostgreSQL relational database populated with IMDB data.

---

## E/R Diagram

Open `notes/movie_recommender_erd_v2.html` in any browser.  
The diagram covers all 13 tables: `MOVIE`, `GENRE`, `MOVIE_GENRE`, `PERSON`,
`MOVIE_PERSON`, `KEYWORD`, `MOVIE_KEYWORD`, `USER`, `USER_MOVIE`, `IMDB_RATING`,
`RECOMMENDATION_SESSION`, `SESSION_BASIS_MOVIE`, `RECOMMENDATION_RESULT`.

---

## Running with Docker (recommended)

Docker is the easiest way to run the app — no Python or PostgreSQL installation needed.

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker + Docker Compose)
- The IMDB dataset files placed in the `notes/` folder:

| File | Download from |
|---|---|
| `title.basics.tsv.gz` | https://datasets.imdbws.com/title.basics.tsv.gz |
| `title.ratings.tsv.gz` | https://datasets.imdbws.com/title.ratings.tsv.gz |
| `title.crew.tsv.gz` | https://datasets.imdbws.com/title.crew.tsv.gz |
| `title.principals.tsv.gz` | https://datasets.imdbws.com/title.principals.tsv.gz |
| `name.basics.tsv.gz` | https://datasets.imdbws.com/name.basics.tsv.gz |

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/frederiksjr/DIS-Project
cd DIS-Project

# 2. Download IMDB data files into notes/ (see table above)

# 3. Build and start the app + database
docker compose up --build -d

# 4. Import IMDB data — only needed once, takes ~5-10 minutes
docker compose exec app python -m app.import_imdb

# 5. Open the app
#    http://localhost:5000
```

To stop: `docker compose down`  
To wipe the database and start fresh: `docker compose down -v`

---

## Running without Docker

### Requirements

- Python 3.12 or later
- PostgreSQL 14 or later
- IMDB dataset files in `notes/` (same files as above)

### Installation

```bash
git clone https://github.com/frederiksjr/DIS-Project
cd DIS-Project

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r app/requirements.txt
```

### Database Setup

```bash
# Create the database (replace 'youruser' with your PostgreSQL username)
createdb moviedb

# Create all tables
DATABASE_URL=postgresql+psycopg://youruser@localhost/moviedb flask --app app init-db

# Import IMDB data (takes ~5-10 minutes)
DATABASE_URL=postgresql+psycopg://youruser@localhost/moviedb python -m app.import_imdb
```

### Running the Application

```bash
DATABASE_URL=postgresql+psycopg://youruser@localhost/moviedb flask --app app run --debug
```

Then open **http://127.0.0.1:5000/** in a browser.

---

## Interaction Instructions

### Getting Recommendations

1. **Movies you've enjoyed** — type one or more movie titles separated by commas.  
   Examples: `Inception`, `The Matrix, Avengers: Endgame, Spider-Man`  
   The search is fuzzy: punctuation and hyphens are ignored, so `Spiderman` finds
   `Spider-Man` and `avengers endgame` finds `Avengers: Endgame`.

2. **Genre** *(optional)* — select a genre to restrict candidates to that genre only.
   Leaving it blank searches across all genres.

3. Click **Get Recommendations →**.

### Reading the Results

Each of the 10 result cards shows:

| Field | Meaning |
|---|---|
| Title + year | The recommended film |
| Genre tags | IMDB genre labels |
| % match | Relative similarity score (top result = 95%, others scaled proportionally) |
| "N users agree" | Number of other users who liked the same basis films and also liked this one |

Click **Try a different search** to return to the form.

---

## How the Algorithm Works

1. **Basis movies** — the films you typed are looked up and used as the starting
   point. Their feature vectors are averaged into a centroid.

2. **Feature vectors** — each movie is encoded as a sparse vector of:
   - Genre membership (one-hot)
   - Top-5-billed actors (weighted `1 / billing_order`) and director (2× weight)
   - Keywords (binary; populated if keyword data is available)
   - Normalised IMDB rating and log-normalised vote count (low weight)

3. **Content score** — cosine similarity between each candidate vector and the
   centroid.

4. **Collaborative score** (`supporting_user_count`) — count of other users who
   liked the same basis films and also liked the candidate.

5. **Final score** — `0.7 × content_similarity + 0.3 × normalised_collaborative`.

### Regex usage

`app/ui.py` uses a compiled regular expression to normalise both the user's search
term and IMDB movie titles before matching, so that punctuation differences
(`Spider-Man` vs `Spiderman`, `Avengers: Endgame` vs `avengers endgame`) do not
prevent a match:

```python
_norm_re = re.compile(r"[^a-z0-9 ]")
norm_term = _norm_re.sub(" ", term.lower()).split()
```

The same pattern is applied to DB titles via PostgreSQL's `regexp_replace`.

---

## Running the Smoke Test

To verify the recommender algorithm without importing IMDB data:

```bash
DATABASE_URL=postgresql+psycopg://youruser@localhost/moviedb python test_recommender.py
```

This inserts five synthetic movies, runs all four recommendation modes, prints
ranked results, and cleans up after itself.

---

## Project Structure

```
app/
  __init__.py          Flask application factory + root redirect
  models.py            SQLAlchemy ORM models (all 13 tables)
  db.py                Engine / session management
  schema.sql           Raw SQL schema (mirrors models.py)
  api.py               JSON REST API (create users, log movies, read results)
  ui.py                HTML UI routes + search normalisation (regex)
  recommender.py       KNN algorithm (feature vectors, cosine similarity)
  import_imdb.py       Bulk import from IMDB .tsv.gz files
  requirements.txt     Python dependencies
  static/css/          Stylesheet
  templates/           Jinja2 HTML templates
notes/
  movie_recommender_erd_v2.html   Interactive E/R diagram
  movie_recommender_schema.md     Schema reference document
test_recommender.py    Standalone algorithm smoke test
```

---

## AI Declaration

Parts of this project were developed with the assistance of Claude (Anthropic).
Claude has been used to help with debugging files, and help setup the docker environment.
All output has been gone through and edited by me.
