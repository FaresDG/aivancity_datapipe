{{ 
  config(
    schema='analytics',
    materialized='table'
  ) 
}}

with possession_events as (
    select
      match_id,
      possession_team_id   as team_id,
      count(*)             as possession_event_count
    from {{ ref('stg_events') }}
    where possession = 1    -- on filtre sur 1 (et non TRUE)
    group by 1, 2
),

total_events_per_match as (
    select
      match_id,
      count(*) as total_events
    from {{ ref('stg_events') }}
    group by 1
),

possession_rate as (
    select
      p.match_id,
      p.team_id,
      p.possession_event_count,
      t.total_events,
      (p.possession_event_count::float / nullif(t.total_events, 0)) as possession_event_ratio
    from possession_events p
    join total_events_per_match t
      on p.match_id = t.match_id
)

select
  match_id,
  team_id,
  possession_event_count,
  total_events,
  possession_event_ratio
from possession_rate
order by match_id, team_id
