{{ config(
    schema='intermediate',
    materialized='table'
) }}

with dates as (
  select distinct
    match_date
  from {{ ref('stg_matches') }}
)

select
  match_date                                           as date,
  extract(year  from match_date)::int                  as year,
  extract(month from match_date)::int                  as month,
  extract(day   from match_date)::int                  as day,
  to_char(match_date, 'Day')                           as weekday
from dates
