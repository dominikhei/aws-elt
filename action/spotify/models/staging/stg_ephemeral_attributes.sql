{{ 
    config(
        materialized="ephemeral"
        )
    }}

SELECT song_id, 
       danceability, 
       energy,        
       acousticness,
       CASE WHEN loudness > 0 THEN loudness * (-1) ELSE loudness END loudness, 
       speechiness, 
       instrumentalness,   
       liveness, 
       valence, 
       tempo, 
       duration_ms 
FROM {{ source("stage_songs", "stg_song_attributes")}}
WHERE song_id IS NOT NULL 
AND duration_ms > 30000
