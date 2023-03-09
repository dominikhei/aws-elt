{{
    config(
        materialized='incremental',
        unique_key='song_id',
        schema="mart"
    )
}}

WITH song_attributes1 AS(
SELECT  DISTINCT song_id, 
        song_name,  
        artist_id, 
        album_id,
        song_duration_ms, 
        explicit, 
        number_on_album,
        CURRENT_DATE AS valid_from,
        '2099-12-31' AS valid_to
FROM {{ source('stage_songs', 'stg_chart_songs') }}
WHERE song_id IS NOT NULL AND artist_id IS NOT NULL AND album_id IS NOT NULL),

song_attributes2 AS(
SELECT DISTINCT song_id, 
       danceability,
       energy,
       loudness, 
       speechiness,
       acousticness, 
       instrumentalness, 
       liveness, 
       valence, 
       tempo, 
       duration_ms
FROM {{ ref('stg_ephemeral_attributes') }}
WHERE song_id IS NOT NULL),

all_attributes_intermediate AS(
SELECT DISTINCT s1.song_id, 
       s1.song_name,  
       s1.artist_id,
       s1.album_id,
       s1.song_duration_ms, 
       s1.explicit, 
       s1.number_on_album,
       s1.valid_from, 
       s1.valid_to, 
       s2.danceability,
       s2.energy,
       s2.loudness, 
       s2.speechiness,
       s2.acousticness, 
       s2.instrumentalness, 
       s2.liveness, 
       s2.valence, 
       s2.tempo,
       CURRENT_DATE AS loaded_at,
FROM song_attributes1 s1 
INNER JOIN song_attributes2 s2 
ON s1.song_id = s2.song_id)

SELECT * FROM all_attributes_intermediate
