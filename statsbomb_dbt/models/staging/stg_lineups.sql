{{ config(materialized='table', schema='staging') }}

select
  match_id,
  team_id,
  player_id,
  player_name,
  player_nickname,
  jersey_number,
  country_id,
  country_name
from {{ source('raw', 'lineups') }}
