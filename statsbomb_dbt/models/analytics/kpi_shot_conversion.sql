{{ 
  config(
    schema='analytics',
    materialized='table'
  ) 
}}

with all_shots as (
    select
      match_id,
      team_id,
      team_name,
      player_id,
      player_name,
      -- on considère qu’un tir converti est un tir dont shot_outcome_name = 'Goal'
      case 
        when shot_outcome_name = 'Goal' then 1 
        else 0 
      end as is_goal
    from {{ ref('stg_events') }}
    where event_type = 'Shot'
),

team_shot_stats as (
    select
      match_id,
      team_id,
      team_name,
      count(*)            as total_shots,
      sum(is_goal)        as total_goals,
      sum(is_goal)::float / nullif(count(*), 0) as team_shot_conversion_rate
    from all_shots
    group by 1, 2, 3
),

player_shot_stats as (
    select
      match_id,
      team_id,
      player_id,
      player_name,
      count(*)            as player_total_shots,
      sum(is_goal)        as player_total_goals,
      sum(is_goal)::float / nullif(count(*), 0) as player_shot_conversion_rate
    from all_shots
    group by 1, 2, 3, 4
)

select
  ts.match_id,
  ts.team_id,
  ts.team_name,
  ts.total_shots,
  ts.total_goals,
  ts.team_shot_conversion_rate,
  ps.player_id,
  ps.player_name,
  ps.player_total_shots,
  ps.player_total_goals,
  ps.player_shot_conversion_rate
from team_shot_stats ts
left join player_shot_stats ps
  on ts.match_id = ps.match_id
 and ts.team_id  = ps.team_id
order by ts.match_id, ts.team_id
