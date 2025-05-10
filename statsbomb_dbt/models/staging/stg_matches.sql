{{  
  config(
    schema='staging',
    materialized='table'
  )  
}}

with raw_matches as (
  select * 
  from {{ source('raw','matches') }}
)

select
  rm.match_id,
  rm.competition_id,
  rm.season_id,
  rm.match_date,
  -- kick_off est déjà de type time
  rm.kick_off::time         as kick_off,
  rm.stadium_id,
  rm.stadium_name,
  rm.stadium_country,
  rm.referee_id,
  rm.referee_name,
  rm.referee_country,
  rm.home_team_id,
  rm.home_team_name,
  rm.home_team_gender,
  rm.away_team_id,
  rm.away_team_name,
  rm.away_team_gender,
  rm.home_score,
  rm.away_score,
  rm.match_status,
  rm.match_week,
  rm.competition_stage_id,
  rm.competition_stage_name,
  rm.last_updated,
  rm.metadata
from raw_matches as rm
