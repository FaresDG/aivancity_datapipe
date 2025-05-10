{{  
  config(
    materialized = "table",
    schema = "staging"
  ) 
}}

select
  competition_id,
  competition_name,
  competition_gender,
  country_name,
  season_id,
  season_name,
  match_updated::timestamp as match_updated,
  match_available::timestamp as match_available
from {{ source('raw','competitions') }}

