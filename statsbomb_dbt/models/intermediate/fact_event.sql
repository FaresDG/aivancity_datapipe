{{ config(
    schema='intermediate',
    materialized='table'
) }}

select
  ev.event_id,
  ev.match_id,
  -- on construit un timestamp à partir de la date du match + heure d'événement
  (m.match_date::timestamp + ev.event_time)       as event_timestamp,
  ev.period,
  ev.event_time,
  ev.team_id,
  ev.team_name,
  ev.player_id,
  ev.player_name,
  ev.position_id,
  ev.position_name,
  ev.location_x,
  ev.location_y,
  ev.duration,
  ev.under_pressure,
  ev.off_camera,
  ev.play_pattern_id,
  ev.play_pattern_name,
  ev.related_events,
  ev.event_type,
  ev.event_details
from {{ ref('stg_events') }}  as ev
join {{ ref('stg_matches') }} as m
  using(match_id)
