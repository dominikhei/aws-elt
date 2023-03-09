{{
    config(
        materialized='incremental',
        unique_key='artist_id',
        schema="mart"
    )
}}

WITH artists_intermediate AS(
SELECT DISTINCT artist_id,
       artist_name,
       CURRENT_DATE as valid_from,
       '2099-12-31' as valid_to,
       CURRENT_DATE AS loaded_at,
FROM {{source('stage_songs', 'stg_chart_songs')}}
WHERE artist_id IS NOT NULL)

SELECT * FROM artists_intermediate