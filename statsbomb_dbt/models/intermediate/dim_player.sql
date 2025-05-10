{{ config(
    schema='intermediate',
    materialized='table'
) }}

select distinct
  player_id,
  player_name,
  player_nickname,
  jersey_number,
  country_id,
  country_name
from {{ ref('stg_lineups') }}
