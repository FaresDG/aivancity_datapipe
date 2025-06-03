{{ 
  config(
    schema='analytics',
    materialized='table'
  ) 
}}

with tackles as (
    select
      match_id,
      team_id,
      team_name,
      player_id,
      player_name,
      -- on considère que tout événement de type 'Duel' avec duel_type_name = 'Tackle' est un tacle
      case 
        when event_type = 'Duel'
         and duel_type_name = 'Tackle' 
         and duel_outcome_name = 'Won'
        then 1
        else 0
      end as is_tackle_won,
      case 
        when event_type = 'Duel'
         and duel_type_name = 'Tackle' 
         and duel_outcome_name = 'Lost'
        then 1
        else 0
      end as is_tackle_lost
    from {{ ref('stg_events') }}
    where event_type = 'Duel'
      and duel_type_name = 'Tackle'
),

interceptions as (
    select
      match_id,
      team_id,
      team_name,
      player_id,
      player_name,
      case 
        when event_type = 'Interception' 
         and interception_outcome_name = 'Successful' 
        then 1
        else 0
      end as is_interception_success
    from {{ ref('stg_events') }}
    where event_type = 'Interception'
),

tackle_summary as (
    select
      match_id,
      team_id,
      team_name,
      sum(is_tackle_won)   as total_tackles_won,
      sum(is_tackle_lost)  as total_tackles_lost,
      (sum(is_tackle_won)::float 
         / nullif(sum(is_tackle_won) + sum(is_tackle_lost), 0)
      ) as tackle_success_rate
    from tackles
    group by 1, 2, 3
),

interception_summary as (
    select
      match_id,
      team_id,
      team_name,
      sum(is_interception_success) as total_interceptions
    from interceptions
    group by 1, 2, 3
)

select
  ts.match_id,
  ts.team_id,
  ts.team_name,
  ts.total_tackles_won,
  ts.total_tackles_lost,
  ts.tackle_success_rate,
  isub.total_interceptions
from tackle_summary ts
left join interception_summary isub
  on ts.match_id = isub.match_id
 and ts.team_id  = isub.team_id
order by ts.match_id, ts.team_id
