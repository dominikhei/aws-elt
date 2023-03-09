{{
    config(
        materialized='incremental',
        unique_key='song_id',
        merge_update_columns = ['last_loaded', 'first_loaded'],
        schema = "mart" 
    )
}}



WITH fact_intermediate AS(
SELECT
st.song_id,
st.album_id,
st.artist_id,
d1.date_id as first_loaded,
d1.date_id as last_loaded,
st.song_duration_ms
FROM {{ source('stage_songs', 'stg_chart_songs') }} st 
JOIN {{ ref("dim_dates") }} d1 ON current_date = d1.year || '-' || d1.month || '-' || d1.day)


SELECT 
fi.song_id, 
fi.artist_id,
fi.album_id,
fi.song_duration_ms, 
fi.last_loaded,
CASE
WHEN current_date - TO_DATE(ll.last_loaded, 'yyyy-mm-dd') > 1 THEN current_date::varchar
ELSE ll.first_loaded
END AS first_loaded
FROM fact_intermediate fi 
INNER JOIN {{ this }} ll
ON fi.song_id = ll.song_id





