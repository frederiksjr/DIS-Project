 CREATE EXTENSION IF NOT EXISTS "pgcrypto";
 
 CREATE TYPE movie_person_role AS ENUM ('actor', 'director');
 CREATE TYPE recommendation_mode AS ENUM ('MOVIE', 'GENRE', 'PROFILE', 'HYBRID');
 
 CREATE TABLE movie (
     imdb_id VARCHAR PRIMARY KEY,
     title VARCHAR NOT NULL,
     release_year INT,
     avg_imdb_rating FLOAT,
     imdb_vote_count INT
 );
 
 CREATE TABLE genre (
     genre_id SERIAL PRIMARY KEY,
     name VARCHAR NOT NULL UNIQUE
 );
 
 CREATE TABLE movie_genre (
     imdb_id VARCHAR NOT NULL REFERENCES movie (imdb_id) ON DELETE CASCADE,
     genre_id INT NOT NULL REFERENCES genre (genre_id) ON DELETE CASCADE,
     PRIMARY KEY (imdb_id, genre_id)
 );
 
 CREATE TABLE person (
     person_id SERIAL PRIMARY KEY,
     imdb_person_id VARCHAR NOT NULL UNIQUE,
     name VARCHAR NOT NULL
 );
 
 CREATE TABLE movie_person (
     imdb_id VARCHAR NOT NULL REFERENCES movie (imdb_id) ON DELETE CASCADE,
     person_id INT NOT NULL REFERENCES person (person_id) ON DELETE CASCADE,
     role movie_person_role NOT NULL,
     billing_order INT NOT NULL,
     PRIMARY KEY (imdb_id, person_id, role)
 );
 
 CREATE TABLE keyword (
     keyword_id SERIAL PRIMARY KEY,
     term VARCHAR NOT NULL UNIQUE
 );
 
 CREATE TABLE movie_keyword (
     imdb_id VARCHAR NOT NULL REFERENCES movie (imdb_id) ON DELETE CASCADE,
     keyword_id INT NOT NULL REFERENCES keyword (keyword_id) ON DELETE CASCADE,
     PRIMARY KEY (imdb_id, keyword_id)
 );
 
 CREATE TABLE "user" (
     user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
     username VARCHAR NOT NULL UNIQUE,
     email VARCHAR NOT NULL UNIQUE,
     password_hash VARCHAR NOT NULL,
     created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
 );
 
 CREATE TABLE user_movie (
     entry_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
     user_id UUID NOT NULL REFERENCES "user" (user_id) ON DELETE CASCADE,
     imdb_id VARCHAR NOT NULL REFERENCES movie (imdb_id) ON DELETE CASCADE,
     liked BOOLEAN NOT NULL,
     user_rating FLOAT,
     logged_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
 );
 
 CREATE TABLE imdb_rating (
     rating_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
     imdb_id VARCHAR NOT NULL REFERENCES movie (imdb_id) ON DELETE CASCADE,
     imdb_user_id VARCHAR NOT NULL,
     rating FLOAT NOT NULL,
     rated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
 );
 
 CREATE TABLE recommendation_session (
     session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
     user_id UUID NOT NULL REFERENCES "user" (user_id) ON DELETE CASCADE,
     genre_id INT REFERENCES genre (genre_id),
     mode recommendation_mode NOT NULL,
     created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
 );
 
 CREATE TABLE session_basis_movie (
     session_id UUID NOT NULL REFERENCES recommendation_session (session_id) ON DELETE CASCADE,
     imdb_id VARCHAR NOT NULL REFERENCES movie (imdb_id) ON DELETE CASCADE,
     excluded BOOLEAN NOT NULL DEFAULT FALSE,
     PRIMARY KEY (session_id, imdb_id)
 );
 
 CREATE TABLE recommendation_result (
     result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
     session_id UUID NOT NULL REFERENCES recommendation_session (session_id) ON DELETE CASCADE,
     imdb_id VARCHAR NOT NULL REFERENCES movie (imdb_id) ON DELETE CASCADE,
     rank INT NOT NULL,
     supporting_user_count INT NOT NULL,
     knn_score FLOAT NOT NULL
 );
