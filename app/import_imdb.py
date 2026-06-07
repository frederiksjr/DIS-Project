import csv
import gzip
import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ["DATABASE_URL"]
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
NOTES = os.path.join(PROJECT_ROOT, "notes")
BATCH_SIZE = 1000

ENGINE = create_engine(DATABASE_URL, future=True)


def iter_tsv(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as file_obj:
        reader = csv.DictReader(file_obj, delimiter="\t")
        for row in reader:
            yield row


def batched(items, size=BATCH_SIZE):
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def parse_int(value):
    return None if value == "\\N" else int(value)


def parse_float(value):
    return None if value == "\\N" else float(value)


def parse_csv_list(value):
    if not value or value == "\\N":
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def load_movies(conn):
    genres = set()
    movie_ids = set()
    movie_stmt = text(
        """
        INSERT INTO movie (imdb_id, title, release_year)
        VALUES (:imdb_id, :title, :release_year)
        ON CONFLICT (imdb_id) DO UPDATE
        SET title = EXCLUDED.title,
            release_year = EXCLUDED.release_year
        """
    )

    movie_batch = []
    for row in iter_tsv(os.path.join(NOTES, "title.basics.tsv.gz")):
        if row["titleType"] != "movie":
            continue
        movie_ids.add(row["tconst"])
        movie_batch.append(
            {
                "imdb_id": row["tconst"],
                "title": row["primaryTitle"],
                "release_year": parse_int(row["startYear"]),
            }
        )
        genres.update(parse_csv_list(row["genres"]))
        if len(movie_batch) >= BATCH_SIZE:
            conn.execute(movie_stmt, movie_batch)
            movie_batch.clear()
    if movie_batch:
        conn.execute(movie_stmt, movie_batch)

    if genres:
        genre_stmt = text(
            """
            INSERT INTO genre (name)
            VALUES (:name)
            ON CONFLICT (name) DO NOTHING
            """
        )
        conn.execute(genre_stmt, [{"name": genre} for genre in sorted(genres)])

    genre_lookup = {name: genre_id for genre_id, name in conn.execute(text("SELECT genre_id, name FROM genre")).all()}

    movie_genre_stmt = text(
        """
        INSERT INTO movie_genre (imdb_id, genre_id)
        VALUES (:imdb_id, :genre_id)
        ON CONFLICT (imdb_id, genre_id) DO NOTHING
        """
    )
    movie_genre_batch = []
    for row in iter_tsv(os.path.join(NOTES, "title.basics.tsv.gz")):
        if row["titleType"] != "movie":
            continue
        for genre in parse_csv_list(row["genres"]):
            movie_genre_batch.append({"imdb_id": row["tconst"], "genre_id": genre_lookup[genre]})
            if len(movie_genre_batch) >= BATCH_SIZE:
                conn.execute(movie_genre_stmt, movie_genre_batch)
                movie_genre_batch.clear()
    if movie_genre_batch:
        conn.execute(movie_genre_stmt, movie_genre_batch)

    return movie_ids


def load_ratings(conn):
    rating_stmt = text(
        """
        UPDATE movie
        SET avg_imdb_rating = :rating,
            imdb_vote_count = :votes
        WHERE imdb_id = :imdb_id
        """
    )
    rating_batch = []
    for row in iter_tsv(os.path.join(NOTES, "title.ratings.tsv.gz")):
        rating_batch.append(
            {
                "imdb_id": row["tconst"],
                "rating": parse_float(row["averageRating"]),
                "votes": parse_int(row["numVotes"]),
            }
        )
        if len(rating_batch) >= BATCH_SIZE:
            conn.execute(rating_stmt, rating_batch)
            rating_batch.clear()
    if rating_batch:
        conn.execute(rating_stmt, rating_batch)


def load_people(conn):
    person_stmt = text(
        """
        INSERT INTO person (imdb_person_id, name)
        VALUES (:imdb_person_id, :name)
        ON CONFLICT (imdb_person_id) DO NOTHING
        """
    )
    person_batch = []
    for row in iter_tsv(os.path.join(NOTES, "name.basics.tsv.gz")):
        person_batch.append({"imdb_person_id": row["nconst"], "name": row["primaryName"]})
        if len(person_batch) >= BATCH_SIZE:
            conn.execute(person_stmt, person_batch)
            person_batch.clear()
    if person_batch:
        conn.execute(person_stmt, person_batch)


def build_person_lookup(conn):
    return {
        imdb_person_id: person_id
        for person_id, imdb_person_id in conn.execute(text("SELECT person_id, imdb_person_id FROM person")).all()
    }


def load_principals(conn, person_lookup, movie_ids):
    movie_person_stmt = text(
        """
        INSERT INTO movie_person (imdb_id, person_id, role, billing_order)
        VALUES (:imdb_id, :person_id, :role, :billing_order)
        ON CONFLICT (imdb_id, person_id, role) DO NOTHING
        """
    )
    principal_batch = []
    for row in iter_tsv(os.path.join(NOTES, "title.principals.tsv.gz")):
        if row["tconst"] not in movie_ids:
            continue
        if row["category"] not in {"actor", "actress"}:
            continue
        person_id = person_lookup.get(row["nconst"])
        if person_id is None:
            continue
        principal_batch.append(
            {
                "imdb_id": row["tconst"],
                "person_id": person_id,
                "role": "actor",
                "billing_order": parse_int(row["ordering"]) or 0,
            }
        )
        if len(principal_batch) >= BATCH_SIZE:
            conn.execute(movie_person_stmt, principal_batch)
            principal_batch.clear()
    if principal_batch:
        conn.execute(movie_person_stmt, principal_batch)


def load_crew_directors(conn, person_lookup, movie_ids):
    director_stmt = text(
        """
        INSERT INTO movie_person (imdb_id, person_id, role, billing_order)
        VALUES (:imdb_id, :person_id, :role, :billing_order)
        ON CONFLICT (imdb_id, person_id, role) DO NOTHING
        """
    )
    director_batch = []
    for row in iter_tsv(os.path.join(NOTES, "title.crew.tsv.gz")):
        if row["tconst"] not in movie_ids:
            continue
        for director in parse_csv_list(row["directors"]):
            person_id = person_lookup.get(director)
            if person_id is None:
                continue
            director_batch.append(
                {
                    "imdb_id": row["tconst"],
                    "person_id": person_id,
                    "role": "director",
                    "billing_order": 0,
                }
            )
            if len(director_batch) >= BATCH_SIZE:
                conn.execute(director_stmt, director_batch)
                director_batch.clear()
    if director_batch:
        conn.execute(director_stmt, director_batch)


def main():
    with ENGINE.begin() as conn:
        movie_ids = load_movies(conn)
        load_ratings(conn)
        load_people(conn)
        person_lookup = build_person_lookup(conn)
        load_principals(conn, person_lookup, movie_ids)
        load_crew_directors(conn, person_lookup, movie_ids)


if __name__ == "__main__":
    main()
