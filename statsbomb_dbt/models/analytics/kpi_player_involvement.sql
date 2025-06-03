{{ 
  config(
    schema='analytics',
    materialized='table'
  ) 
}}

with all_events_by_player as (
    select
      match_id,
      team_id,
      player_id,
      player_name,
      -- chaque ligne où player_id n'est pas null est comptée comme une “touche”
      1 as is_touch,
      -- on récupère shot_assist depuis event_details JSON : 'true' → 1, sinon 0
      case
        when event_type = 'Pass'
         and (event_details ->> 'shot_assist')::text = 'true'
        then 1
        else 0
      end as is_key_pass
    from {{ ref('stg_events') }}
    where player_id is not null
),

player_summary as (
    select
      match_id,
      team_id,
      player_id,
      player_name,
      sum(is_touch)     as total_touches,
      sum(is_key_pass)  as total_key_passes
    from all_events_by_player
    group by 1, 2, 3, 4
)

select
  match_id,
  team_id,
  player_id,
  player_name,
  total_touches,
  total_key_passes,
  case 
    when total_touches > 0 
    then total_key_passes::float / total_touches 
    else null 
  end as key_pass_rate
from player_summary
order by match_id, team_id, player_id
