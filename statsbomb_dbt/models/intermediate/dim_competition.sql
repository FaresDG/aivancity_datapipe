{{ 
  config(
    schema='intermediate',
    materialized='table'
  )
}}

with competitions as (
  select
    competition_id,
    competition_name,
    competition_gender,
    country_name            as competition_country,
    season_id,
    season_name
  from {{ ref('stg_competitions') }}
)

select distinct
  competition_id,
  competition_name,
  competition_gender,
  competition_country,
  season_id,
  season_name
from competitions
order by competition_id
