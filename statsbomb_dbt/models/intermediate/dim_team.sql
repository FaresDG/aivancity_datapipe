{{ config(
    schema='intermediate',
    materialized='table'
) }}

with both_teams as (
  select home_team_id as team_id, home_team_name as team_name, home_team_gender as team_gender
    from {{ ref('stg_matches') }}
  union
  select away_team_id, away_team_name, away_team_gender
    from {{ ref('stg_matches') }}
)

select distinct
  team_id,
  team_name,
  team_gender
from both_teams
