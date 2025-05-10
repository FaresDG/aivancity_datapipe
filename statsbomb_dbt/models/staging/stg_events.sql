-- models/staging/stg_events.sql

{{
  config(
    materialized = 'table',
    schema       = 'staging'
  )
}}

select
  ev.event_id             as event_id,
  ev.match_id             as match_id,
  ev.period               as period,
  ev.timestamp::time      as event_time,
  ev.team_id              as team_id,
  ev.team_name            as team_name,
  ev.player_id            as player_id,
  ev.player_name          as player_name,
  ev.position_id          as position_id,
  ev.position_name        as position_name,
  ev.location_x           as location_x,
  ev.location_y           as location_y,
  ev.duration             as duration,
  ev.under_pressure       as under_pressure,
  ev.off_camera           as off_camera,
  ev.play_pattern_id      as play_pattern_id,
  ev.play_pattern_name    as play_pattern_name,
  ev.related_events       as related_events,
  ev.event_type           as event_type,
  ev.event_details        as event_details
from {{ source('raw', 'events') }} as ev
