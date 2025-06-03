{{ 
  config(
    schema='analytics',
    materialized='table'
  ) 
}}

with all_passes as (
    select
      match_id,
      team_id,
      team_name,
      player_id,
      player_name,
      -- Dans stg_events, pass_outcome_name = 'Complete' si la passe a été réussie
      case 
        when pass_outcome_name = 'Complete' then 1 
        else 0 
      end as is_completed
    from {{ ref('stg_events') }}
    where event_type = 'Pass'
),

-- On calcule l’indicateur par équipe/par match
team_accuracy as (
    select
      match_id,
      team_id,
      team_name,
      sum(is_completed)::float / nullif(count(*), 0) as team_passing_accuracy
    from all_passes
    group by 1, 2, 3
),

-- On calcule l’indicateur par joueur/par match (optionnel)
player_accuracy as (
    select
      match_id,
      team_id,
      player_id,
      player_name,
      sum(is_completed)::float / nullif(count(*), 0) as player_passing_accuracy
    from all_passes
    group by 1, 2, 3, 4
)

select 
  ta.match_id,
  ta.team_id,
  ta.team_name,
  ta.team_passing_accuracy,
  pa.player_id,
  pa.player_name,
  pa.player_passing_accuracy
from team_accuracy ta
left join player_accuracy pa
  on ta.match_id   = pa.match_id
 and ta.team_id    = pa.team_id
order by ta.match_id, ta.team_id
