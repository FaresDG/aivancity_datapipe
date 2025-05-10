-- create_tables.sql

-- 1. competitions
CREATE TABLE IF NOT EXISTS competitions (
  competition_id      INTEGER NOT NULL,
  season_id           INTEGER NOT NULL,
  competition_name    TEXT,
  competition_gender  TEXT,
  country_name        TEXT,
  season_name         TEXT,
  match_updated       TIMESTAMP,
  match_available     TIMESTAMP,
  PRIMARY KEY (competition_id, season_id)
);

-- 2. matches
CREATE TABLE IF NOT EXISTS matches (
  match_id               INTEGER PRIMARY KEY,
  competition_id         INTEGER NOT NULL,
  season_id              INTEGER NOT NULL,
  match_date             DATE,
  kick_off               TIME,
  stadium_id             INTEGER,
  stadium_name           TEXT,
  stadium_country        TEXT,
  referee_id             INTEGER,
  referee_name           TEXT,
  referee_country        TEXT,
  home_team_id           INTEGER,
  home_team_name         TEXT,
  home_team_gender       TEXT,
  away_team_id           INTEGER,
  away_team_name         TEXT,
  away_team_gender       TEXT,
  home_score             INTEGER,
  away_score             INTEGER,
  match_status           TEXT,
  match_week             INTEGER,
  competition_stage_id   INTEGER,
  competition_stage_name TEXT,
  last_updated           TIMESTAMP,
  metadata               JSONB,
  FOREIGN KEY (competition_id, season_id)
    REFERENCES competitions (competition_id, season_id)
);

-- 3. lineups
CREATE TABLE IF NOT EXISTS lineups (
  match_id        INTEGER NOT NULL,
  team_id         INTEGER NOT NULL,
  player_id       INTEGER NOT NULL,
  player_name     TEXT,
  player_nickname TEXT,
  jersey_number   INTEGER,
  country_id      INTEGER,
  country_name    TEXT,
  PRIMARY KEY (match_id, team_id, player_id),
  FOREIGN KEY (match_id) REFERENCES matches (match_id)
);

-- 4. events (with `is_out` instead of `out`)
CREATE TABLE IF NOT EXISTS events (
  event_id           UUID PRIMARY KEY,
  match_id           INTEGER NOT NULL,
  period             INTEGER,
  timestamp          TEXT,
  team_id            INTEGER,
  team_name          TEXT,
  player_id          INTEGER,
  player_name        TEXT,
  position_id        INTEGER,
  position_name      TEXT,
  location_x         NUMERIC,
  location_y         NUMERIC,
  duration           NUMERIC,
  under_pressure     BOOLEAN,
  off_camera         BOOLEAN,
  is_out             BOOLEAN,
  play_pattern_id    INTEGER,
  play_pattern_name  TEXT,
  related_events     JSONB,
  event_type         TEXT,
  event_details      JSONB,
  FOREIGN KEY (match_id) REFERENCES matches (match_id)
);

