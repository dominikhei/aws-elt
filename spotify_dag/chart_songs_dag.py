from airflow import DAG
from airflow.providers.amazon.aws.operators.redshift_sql import RedshiftSQLOperator
from airflow.providers.amazon.aws.transfers.s3_to_redshift import S3ToRedshiftOperator
from airflow.operators.bash import BashOperator
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
from airflow.providers.amazon.aws.transfers import s3_to_redshift
from airflow.operators.python import BranchPythonOperator, PythonOperator
from airflow.operators.dummy import DummyOperator
from datetime import date, timedelta, datetime
from dotenv import load_dotenv
import os
from soda.scan import Scan
from airflow.hooks.base import BaseHook
from airflow.providers.amazon.aws.operators.ecs import (
    EcsDeregisterTaskDefinitionOperator,
    EcsRegisterTaskDefinitionOperator,
    EcsRunTaskOperator,
    EcsTaskDefinitionStateSensor
)
from airflow.providers.amazon.aws.hooks.ecs import EcsTaskStates
from airflow.providers.amazon.aws.sensors.ecs import EcsTaskStateSensor

redshift_connection = BaseHook.get_connection("redshift-spotify")
aws_iam = BaseHook.get_connection("aws-iam")
spotify_keys = BaseHook.get_connection("Spotify_Api_Tokens")


def run_checks_soda():
    scan = Scan()
    scan.set_data_source_name("redshift_spotify_charts")
    scan.add_variables({"ACCESS_KEY": aws_iam.login})
    scan.add_variables({"SECRET_ACCESS_KEY": aws_iam.password})
    scan.add_variables({"REDSHIFT_HOST": redshift_connection.host})
    scan.add_variables({"REDSHIFT_PW": redshift_connection.password})
    scan.add_configuration_yaml_file(file_path="/opt/airflow/dags/spotify_dag/soda_test/configuration.yml")
    scan.add_sodacl_yaml_file("/opt/airflow/dags/spotify_dag/soda_test/checks.yml")

    scan.execute()

    if scan.has_check_fails():
        return "checks_failed"
    else:
        return "checks_succeeded"

def fail_dag():
    raise ValueError
    

default_args = default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2023,2,5),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=5)
}

dag = DAG(
    'spotify_charts_dag',
    default_args=default_args,
    description='',
    schedule_interval=None,
)


extract_and_upload_to_s3 = BashOperator(
    task_id="extract_and_upload_to_s3",
    bash_command="python3 /opt/airflow/dags/spotify_dag/extract_data.py",
    env={"CLIENTID": spotify_keys.login, "CLIENTSECRET": spotify_keys.password},
    dag = dag
)


today = date.today()

s3_filesensor_attributes = S3KeySensor(
    task_id = "check_attribute_file_exists",
    bucket_key = f"raw/song_attributes/{today}/song_attributes.csv",
    bucket_name="spotify-project1",
    aws_conn_id='aws-iam',
    dag = dag
)


s3_filesensor_songs = S3KeySensor(
    task_id = "check_songs_file_exists",
    bucket_key = f"raw/chart_songs/{today}/songs.csv",
    bucket_name="spotify-project1",
    aws_conn_id='aws-iam',
    dag = dag
)


create_songs_stage = RedshiftSQLOperator(
    task_id='create_songs_stage',
    redshift_conn_id = "redshift-spotify",
    sql = """
          CREATE TABLE IF NOT EXISTS spotify_project.stage.stg_chart_songs(
          song_id varchar(22),
          song_name varchar(200),
          artist_name varchar(200),
          artist_id varchar(22),
          number_on_album smallint,
          song_duration_ms BIGINT,
          popularity smallint,
          explicit BOOLEAN,
          album_id varchar(22),
          album_name varchar(200),
          album_release_date Date,
          album_total_tracks smallint
);""",
    dag = dag
)


create_attributes_stage = RedshiftSQLOperator(
    task_id='create_attributes_stage',
    redshift_conn_id = "redshift-spotify",
    sql = """
          CREATE TABLE IF NOT EXISTS spotify_project.stage.stg_song_attributes(
          song_id varchar(22),
          danceability double precision,
          energy double precision,
          loudness double precision,
          speechiness double precision,
          acousticness double precision,
          instrumentalness double precision,
          liveness double precision,
          valence double precision,
          tempo double precision,
          duration_ms BIGINT
          );""",
    dag = dag
)


copy_in_song_attributes_stage = S3ToRedshiftOperator(
    task_id = "copy_in_song_attributes_stage",
    aws_conn_id='aws-iam',
    redshift_conn_id = "redshift-spotify",
    s3_bucket = "spotify-project1",
    s3_key = f"raw/song_attributes/{today}/song_attributes.csv",
    schema = "stage",
    table = "stg_song_attributes",
    copy_options=["csv", "IGNOREHEADER 1"],
    dag = dag
)


copy_in_chart_songs_stage = S3ToRedshiftOperator(
    task_id = "copy_in_chart_songs_stage",
    aws_conn_id='aws-iam',
    redshift_conn_id = "redshift-spotify",
    s3_bucket = "spotify-project1",
    s3_key = f"raw/chart_songs/{today}/songs.csv",
    schema = "stage",
    table = "stg_chart_songs",
    copy_options=["csv", "IGNOREHEADER 1"],
    dag = dag
)


stage_data_tests = BranchPythonOperator(
    task_id="stage_data_tests",
    python_callable=run_checks_soda,
    dag=dag
)

checks_failed = DummyOperator(
task_id='checks_failed',
dag=dag
)

checks_succeeded = DummyOperator(
task_id='checks_succeeded',
dag=dag
    )

fail_dag = BranchPythonOperator(
    task_id = "fail_dag",
    python_callable=fail_dag,
    retries=0,
    dag=dag
)

truncate_stage_chart_songs = RedshiftSQLOperator(
    task_id='truncate_stage_songs',
    redshift_conn_id = "redshift-spotify",
    sql = "TRUNCATE TABLE spotify_project.stage.stg_chart_songs;",
    dag = dag
)

truncate_stage_song_attributes = RedshiftSQLOperator(
    task_id='truncate_stage_attributes',
    redshift_conn_id = "redshift-spotify",
    sql = "TRUNCATE TABLE spotify_project.stage.stg_song_attributes;",
    dag = dag
)


register_task = EcsRegisterTaskDefinitionOperator(
    task_id="register_dbt_chart_task",
    family="dbt",
    wait_for_completion=False,
    container_definitions=[
        {
            "name": "dbt_spotify_charts",
            "image": "__INSERT_DBT_IMAGE_URI_HERE__",
            "workingDirectory": "/dbt_project",
            "entryPoint": ["bash", "dbt run"],
            "environment": [ 
            { 
               "name": "REDSHIFT_HOST",
               "value": redshift_connection.host
            },
            {
                "name": "REDSHIFT_USER",
                "value": redshift_connection.user
            },            
            {   "name": "REDSHIFT_PW",
                "value": redshift_connection.password}
         ]
        }
    ],
    register_task_kwargs={
        "executionRoleArn": "___INSERT_THE_EC2_ROLE_ARN_HERE",
        "requiresCompatibilities": ["FARGATE"], 
        "cpu": "256",
        "memory": "512",
        "networkMode": "awsvpc"
    },
    aws_conn_id="aws-iam",
    dag=dag
)

await_task_definition = EcsTaskDefinitionStateSensor(
    task_id="await_task_definition",
    task_definition=register_task.output,
    aws_conn_id="aws-iam",
    dag=dag,
)

run_dbt_container = EcsRunTaskOperator(
    task_id="run_dbt_container",
    cluster="dbt-cluster",
    task_definition=register_task.output,
    aws_conn_id="aws-iam",
    launch_type="FARGATE",
    overrides={
        "containerOverrides": [
            {
                "name": "dbt_spotify_charts",
                "command": ["echo", "hello", "world"],
            },
        ],
    },
    network_configuration={
        "awsvpcConfiguration": {
            "subnets": ["__ENTER_THE_SPOTIFY_SUBNET_ID_HERE__"],    
            "securityGroups": ["__ENTER_THE_PROJECT_SECURITY_GROUP_HERE__"],
            "assignPublicIp": "ENABLED",
        },
    },
    dag=dag
)

deregister_task = EcsDeregisterTaskDefinitionOperator(
    task_id="deregister_task",
    task_definition=register_task.output,
    aws_conn_id="aws-iam",
    dag=dag
)

truncate_stage_chart_songs_2 = RedshiftSQLOperator(
    task_id='truncate_stage_songs_2',
    trigger_rule='all_done',
    redshift_conn_id = "redshift-spotify",
    sql = "TRUNCATE TABLE spotify_project.stage.stg_chart_songs;",
    dag = dag
)

truncate_stage_song_attributes_2 = RedshiftSQLOperator(
    task_id='truncate_stage_attributes_2',
    trigger_rule='all_done',
    redshift_conn_id = "redshift-spotify",
    sql = "TRUNCATE TABLE spotify_project.stage.stg_song_attributes;",
    dag = dag
)


extract_and_upload_to_s3 >> [s3_filesensor_songs, s3_filesensor_attributes ] 

s3_filesensor_songs >> create_songs_stage >> copy_in_chart_songs_stage

s3_filesensor_attributes >> create_attributes_stage >> copy_in_song_attributes_stage

[copy_in_chart_songs_stage, copy_in_song_attributes_stage] >> stage_data_tests >> [checks_failed, checks_succeeded]

checks_failed >> truncate_stage_chart_songs >> truncate_stage_song_attributes >> fail_dag

checks_succeeded >> register_task >> await_task_definition >> run_dbt_container

run_dbt_container >> deregister_task >> truncate_stage_chart_songs_2

deregister_task >> truncate_stage_song_attributes_2

