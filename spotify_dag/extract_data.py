import requests
import base64
from requests.adapters import HTTPAdapter
from dotenv import load_dotenv
import os
import boto3
import json
from datetime import date
import botocore.exceptions as aws_exception
import time
import pandas as pd
from io import StringIO

load_dotenv()
CLIENTID = os.getenv('CLIENTID')
CLIENTSECRET = os.getenv('CLIENTSECRET')




def get_token():
    """
    Returns a valid API token
    """
    url = 'https://accounts.spotify.com/api/token'
    headers = {}
    data = {'grant_type' : "client_credentials"}

    message = f"{CLIENTID}:{CLIENTSECRET}"
    messageBytes = message.encode('ascii')
    base64Bytes = base64.b64encode(messageBytes)
    base64Message = base64Bytes.decode('ascii')

    headers['Authorization'] = f"Basic {base64Message}"
    r = requests.post(url, headers=headers, data=data)
    token = r.json()['access_token']
    return token


def create_header(token):
    """
    Returns the header for the Spotify API request.
    """

    header = {
              "Accept" : "application/json",
              "Content-Type" : "application/json",
              "Authorization" : "Bearer {token}".format(token=token)
              }
    return header


def extract_data(url, header, max_retries=5):
    """
    Reusable function, to make get requests to the spotify API
    """
    session = requests.Session()
    retry = HTTPAdapter(max_retries=max_retries)
    session.mount('https://', retry)
    session.mount('http://', retry)
    
    try:
        response = session.get(url, headers=header, params={"limit": 50})
        data = response.json()
        return data
    except (ConnectionError, requests.exceptions.Timeout) as err:
        print(f"Failed to connect to the API, retrying... Error: {err}")
        extract_data(url, header, max_retries)
    except requests.exceptions.TooManyRedirects as err:
        print("Bad URL, try a different one")
        raise SystemExit(err)
    except requests.exceptions.HTTPError as err:
        raise SystemExit(err)


def transform_chart_json(data):
        """
        Only puts the needed key/value pairs in a Json
        """
        songs = [{"song_id": song["track"]["id"],
              "song_name": song["track"]["name"],
              "artist_name": song["track"]["artists"][0]["name"],
              "artist_id": song["track"]["artists"][0]["id"],
              "number_on_album": song["track"]["track_number"],
              "song_duration_ms": song["track"]["duration_ms"],
              "popularity": song["track"]["popularity"],
              "explicit": song["track"]["explicit"],
              "album_id": song["track"]["album"]["id"],
              "album_name": song["track"]["album"]["name"],
              "album_release_date": song["track"]["album"]["release_date"],
              "album_total_tracks": song["track"]["album"]["total_tracks"]}
             for song in data["items"]]
        
        songs = pd.DataFrame(songs)
        return songs


def extract_attribute_data(data):
    """
    Function to extract attributes for all of the songs in the charts 
    """
    attributes = []

    for i in range(len(data)):

        song_id = data['song_id'][i]
        ATTRIBUTE_URL = 'https://api.spotify.com/v1/audio-features/{0}'.format(song_id)
        result_data = extract_data(ATTRIBUTE_URL, header, max_retries=5)

        attributes.append({
            "song_id": result_data["id"],
            "danceability": result_data["danceability"],
            "energy": result_data["energy"],
            "loudness": result_data["loudness"],
            "speechiness": result_data["speechiness"],
            "acousticness": result_data["acousticness"],
            "instrumentalness": result_data["instrumentalness"],
            "liveness": result_data["liveness"],
            "valence": result_data["valence"],
            "tempo": result_data["tempo"],
            "duration_ms": result_data["duration_ms"]
        })
    attributes = pd.DataFrame(attributes)
    return attributes



def create_s3_ressource():
    """
    This function creates a connection to s3 based on the credentials in the .env file
    """
    session = boto3.Session()
    s3_client = session.client('s3')

    return s3_client



def upload_csv_to_s3(data, bucket_name, upper_folder, max_retries, delay_seconds, file_name):
    """
    Uploads the Csv to S3
    """
    s3_client = create_s3_ressource()
    todays_date = date.today()
    key_prefix= f"{upper_folder}/{todays_date}/{file_name}"
    csv_buf = StringIO()
    data.to_csv(csv_buf, header=True, index=False)

    for i in range(max_retries):
        try:
            s3_client.put_object(Bucket=bucket_name, Body=csv_buf.getvalue(), Key=key_prefix)
            break
        except aws_exception.ClientError as e:
            if e.response['Error']['Code'] == "NoSuchBucket":
                print("Bucket does not exist, please check: ", e)
            elif e.response['Error']['Code'] == "ServiceUnavailable":
                if i == max_retries - 1:
                    raise e
                else:
                    print(f"Upload failed: {e}, retrying in {delay_seconds} seconds")
                    time.sleep(delay_seconds)
                    delay_seconds *= 2
            else:
                raise e
        except aws_exception.EndpointConnectionError as e:
            if i == max_retries - 1:
                raise e
            else:
                print(f"Upload failed: {e}, retrying in {delay_seconds} seconds")
                time.sleep(delay_seconds)
                delay_seconds *= 2


if __name__ == "__main__":
    BASE_URL = 'https://api.spotify.com/v1/'
    PLAYLIST_URI = '37i9dQZEVXbMDoHDwVN2tF'
    CHARTS_URL = BASE_URL + 'playlists/' + PLAYLIST_URI +'/tracks'
    token = get_token()
    header = create_header(token)
    data = extract_data(CHARTS_URL, header, max_retries=5)
    data = transform_chart_json(data)
    upload_csv_to_s3(data, "spotify-project1", "raw/chart_songs", 3, 5, "songs.csv")

    ATTRIBUTE_URL = f'https://api.spotify.com/v1/v1/audio-analysis/{id}'
    token = get_token()
    header = create_header(token)
    attributes = extract_attribute_data(data)
    upload_csv_to_s3(attributes, "spotify-project1", "raw/song_attributes", 3, 5, "song_attributes.csv")