{{
    config(
        materialized='incremental',
        unique_key='date_id',
        schema="mart"
    )
}}

WITH first_dates as( 
SELECT CONCAT(SUBSTRING(CAST(CURRENT_DATE AS TEXT),1,4), CONCAT(SUBSTRING(CAST(CURRENT_DATE AS TEXT),6,2), SUBSTRING(CAST(CURRENT_DATE AS TEXT),9,2))) as date_id,
SUBSTRING(CAST(CURRENT_DATE AS TEXT),1,4) AS year,
SUBSTRING(CAST(CURRENT_DATE AS TEXT),6,2) AS month,
SUBSTRING(CAST(CURRENT_DATE AS TEXT),9,2) AS day
FROM {{source('stage_songs', 'stg_chart_songs')}}),

second_dates as(
SELECT CONCAT(SUBSTRING(CAST(album_release_date AS TEXT),1,4), CONCAT(SUBSTRING(CAST(album_release_date AS TEXT),6,2), SUBSTRING(CAST(album_release_date AS TEXT),9,2))) as date_id,
SUBSTRING(CAST(album_release_date AS TEXT),1,4) AS year,
SUBSTRING(CAST(album_release_date AS TEXT),6,2) AS month,
SUBSTRING(CAST(album_release_date AS TEXT),9,2) AS day
FROM {{ source('stage_songs', 'stg_chart_songs')}}
), 

both_dates_intemediate AS(
SELECT DISTINCT date_id, year, month, day FROM first_dates
UNION ALL 
SELECT DISTINCT date_id, year, month, day FROM second_dates
)

SELECT DISTINCT date_id, year, month, day FROM both_dates_intemediate