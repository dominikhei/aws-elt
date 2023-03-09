{{
    config(
        materialized='incremental',
        unique_key='album_id',
        schema='mart'
    )
}}


WITH albums_intermediate AS(
SELECT DISTINCT s.album_id,
       s.album_name,
       s.artist_id,
       d.date_id AS date_id_release_date,
       s.album_total_tracks,
       CURRENT_DATE AS loaded_at,
FROM {{source('stage_songs', 'stg_chart_songs')}} s
JOIN {{ ref('dim_dates') }} d ON CONCAT(SUBSTRING(CAST(s.album_release_date AS TEXT),0,4),CONCAT(SUBSTRING(CAST(s.album_release_date AS TEXT),6,2),SUBSTRING(CAST(s.album_release_date AS TEXT),9,2))) = d.date_id)

SELECT * FROM albums_intermediate