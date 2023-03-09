## Structure 
- [Introduction](#introduction)
- [ELT process walkthrough](#process:)
- [Handling Idempotency](#handling-idempotency:)
- [Architecture on AWS](#architecture)
- [Extraction code walkthrough](#extraction-code-walkthrough:)
- [How to set the project up locally](#how-to-set-the-project-up-locally:)
- [Future outlook](#future-outlook)


## Introduction

I was intrigued to explore the common attributes of songs that make it to the Spotify charts. 
To be able to analyse this, I have built an ELT Pipeline on AWS. The AWS Infrastructure is spun up using Terraform, which makes it easy to understand and replicate. The whole pipeline is scheduled by Apache Airflow and the Transformation are carried out by DBT. 

I have used an __ELT process__ for this pipeline, __here is why__:
ELT means to transform the data after it has been loaded into its destination. 
I am doing this, because modern cloud infrastructure has become way cheaper, which makes it less of a concern to store large amounts of untransformed raw data. Furthermore modern Data Warehouses have a lot of processing power, eliminating the need for external frameworks to transform the data. The result is a highly scalable architecture. 

## ELT process:

__Note:__ This is the process described from a non infrastructural perspective. How all of these parts have been set up / deployed can be found [here](#architecture)

I have made sure that the complete process is __idempotent__, which means that if it accidently runs twice per day no additional data is being inserted and thus no false records are being created. More on this [here](#handling-idempotency)

__Extracting:__

I am extracting the songs currently in the charts and their attributes daily from 2 Spotify API endpoints using a Python script. This data is not being futher processed.

__Loading:__

The results are loaded into an S3 bucket in the raw zone. This folder (folders are actually prefixes to an objects key in S3) is again split in a *chart_songs* and a *song_attributes* folder. Inside them the Script dynamically creates new folders for the current day and uploads the 2 datasets using the boto3 library to make calls to the S3 Api. In the next step, both files will be copied in the matching Redshift stage tables.

__Transforming:__

Transformations are being handled by DBT. The data is stored in a typical star schema, as made popular by Ralph Kimball. 
![](/.images/star-schema.png)
As you can see, I have added __part 2 slowly changing dimensions__ for the dim_arists table. This is because artists might change their name. Moreover all tables have a loaded_at column, as an audit field. 

Before the DBT models are being executed I run __schema and data quality checks__ on the data in the stage tables. If these fail, the tables will be truncated again.
For these checks I use a yml based framework called __soda-core__. 
I run the following checks using Python:

- Does the data in the stage tables match a schema 
- Have both tables got the same amount of records 
- Do the column values fall in a predefined range

The folder with the checks can be found [here](/spotify_dag/soda_test/)
Once these checks are being passed, DBT executes the transformations.
I have used incremental models in DBT, which means that data is only being inserted if the record does not exist. If it already exists, I update only two columns in the fact table. The last_loaded column, which is set to the current date and the first_loaded column, which is only changed, if last_loaded is older than two days, which means the song hast left the charts and now enters for a second time. Then it is also set to the current date. 
After the Transformations have been done, the stage tables are being truncated. The raw data will be kept permanent in the S3 bucket. 

![](/.images/dag.png)
This is the corresponding Airflow dag, which can be found [here](/spotify_dag/chart_songs_dag.py).

The truncate_stage_attributes2 and truncate_stage_songs2 tasks are also being executed if any of the upstream tasks fail, which means that these tables will always be empty after a run, no matter its state. By that I am ensuring idempotency. 

## Handling Idempotency:

One of the largest concerns when building a data pipeline is wheter it is idempotent. This means that the pipeline can be executed multiple times, without changing the data in our sink. Or for anyone with a mathematical background: f(f(x)) = f(x). This pipeline is idempotent, let me show you why: 

- If you extract the charts_data multiple times within a day, it will not change, since the charts are only updated at the beginning of a day and just overwrite the already existing files in S3 with the same data.

- Since the Redshift stage tables are always truncated no matter how the process ends, there will be no duplicates in them.

- The dimensional tables are built with an incremental strategy, meaning already existing records will not be inserted again. Since the raw data will not change compared to the last run, nothing will be inserted in case of a duplicated run. 

- In the fact table we also only insert new records or update the date columns for the already existing ones. In our case the difference between the last_loaded column in the fact table and the current date will be 0 days -> No update of this column. This also means that first_loaded will not be updated. I have explained the logic behind these updates under __Transforming__ in the section above. 

As you can see, no matter how often you run the pipeline after your initial daily run, the data in the DWH will never be invalidated. This means that the pipeline is indempotent. 

## Architecture
![](/.images/architecture.png)

This Section explains the AWS Infrastructure, which has been created using Terraform. I have broken it down into the following subsections:

__Security group and outside access:__

The EC2 Instance and Redshift Cluster are in its own security group, which allows the following inbound / outbound access:

- Ingress rules:
   - Allow any traffic from within the security group 
   - Port 22 access from your local machine (to ssh into the EC2 instance)
   - Port 8080 access from your local machine (to access the Airflow web ui)

- Egress rules:
    - Full egress (to download Airflow and Python packages to the EC2 instance)

The Fargate Task will also run within this security group, allowing DBT to access Redshift without making the cluster publicly accessible. 

__IAM Access:__

The terraform scripts creates 2 IAM Roles and 1 User with access keys, which has ECR access. This is unfortunately needed for Github Actions. The 2 IAM Roles are being attatched to Redshift and EC2 and are later assumed by Airflow, *which eliminated the need for access keys*. A general rule is to avoid keys and never create them for your root user. 

The I AM Roles have full access for all the service they need to access. This is also something that should be avoided, which I nevertheless have kept for simplicity reasons. 

__Deployment of Apache Airflow:__

Airflow is deployed in an EC2 t2.medium instance using docker compose. Installation of Airflow and required Python packages as well as adding the needed connections to the backend is also automatically done by Terraform. This way of deployment is valid for testing and personal project purpose, in a production environment one would use f.e __Kubernetes__ to ensure that Airflow is constantly running. Since The attatched I-AM Role has access to all other services of this project, Airflow can assume it and execute the AWS tasks in the dag without storing sensitive credentials in its backend.  

__Deployment of DBT:__

The local DBT project is linked to a Github repository. Once something is commited, Github Actions builds a new Docker image based on the DBT project and pushes it to a private repository in AWS ECR. The used base-image is the *python:3.11-slim* which ensures minimal storage usage.
I have deployed DBT in a Docker container instead of having the project stored on the same EC2 Instance as Airflow, to seperate the parts and ensure better scalability.

__Execution of DBT:__

Once a DBT project needs to be executed, Airflow registers a new AWS Fargate Task which builds a Docker container based on the image in ECR and executes it with the entrypoint dbt deps & dbt run. After execution, the task will be deregistered again. 

*Why have I chosen Fargate over ECS container instances?*

In comparison to ECS container instances, one does not need to manage an EC2 Instance in the background anymore and Fargate manages everything for me. This significantly reduces the operational effort. 

__S3 storage:__

The Raw data is stored in S3 in a Raw layer, in folders which indicate the day of creation. This makes it easy to move the API returns to Redshift, with the RedshiftCopy command and the raw data is cheaply stored for further use cases. 
The structure of the projects S3 bucket looks like the following:

- Raw 
    - chart_songs
        - folders with dates
    - song_attributes
        - folders with dates

__Redshift:__

Redshift is AWS own Data Warehouse, based on Postgres. The Redshift database has two schemas: stage and mart. This is to seperate the actual data and the staging data and thus helps to organize everything. Redshift is set to not publicly accessible. 

__VPC setup__

As explained, Redshift and The EC2 instance are in its own VPC. Through the associated security group all services within the VPC can share data unrestricted between each other, this is why I launch the Fargate task in that subnet too, because than DBT can access redshift, whcih would not be possible from outside the VPC.

This is the VPC setup visualized:
![](/.images/vpc.png)

## Extraction code walkthrough:

Here I am walking you through the script which extracts the song_data from Spotifys Api endpoints and loads them in S3. The actual script can be found [here](/spotify_dag/extract_data.py)

This function creates an Api access token. This is especially helpfull since the Spotify API tokens expire after some time, so simply storing one as a variable would not work. The clientId and clientSecret are passed as environment variables via the Airflow task.
This means that no secrets are stored in env files or are encoded. Instead they will be set in Terraform as varibales and when creating the infrastructure they are passed into Airflows secrets backend. 

![](/.images/get-token.png)

This is the function to make a get request to the Api. if you have connection errors, the function will wait some time and try it again later. 

![](/.images/extract-data.png)

To copy data from S3 to redshift, it is very helpfull if the data is already in a relational format like Csv. This function transforms the Json response into a pandas dataframe which will later be uploaded to S3 as a Csv file. 

![](/.images/transform-chart-json.png)

For each of these songs, I am making a call to a different Api endpoint, to extract data on the songs attributes.

![](/.images/extract_attribute_data.png)

Last, the data needs to be uploaded to S3 as a Csv file using boto3. This function also creates a folder with the current date, in which the file will be put to sort everything.  

![](/.images/upload-csv-to-s3.png)



## How to set the project up locally:

To set the project up yourself, you need:
- The AWS Cli 
- Terraform 
- An Unix terminal
- An AWS account

You can set up the AWS Cli according to [this guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)

Then cd into the [terraform folder](/terraform/) and enter the command terraform init. After that you need to run terraform apply, this will create the defined infrastructure on AWS for you. __Attention:__ The services that are being used in this project cost money, I am by no way accountable for any charges that occur for you. 

You now need to log into the AWS Web UI and create access_key and secret_access_key for the Github Actions user, remember these since you can only view them once and later need to put them into Github Actions.

__Create a DBT image via Github Actions__

You first need to create a __private__ remote Github repository without a readme and add the beforehand created access_key and secret_access_key.
This can be done in the Repository Web UI under: 

Settings/Secrets and variables/Actions

Next init a Git repository in the [action folder](/action/) and add your beforehand created remote. After that push everything to the remote. Github Actions will create a new Docker Image with the DBT project and push it to AWS ECR.

Once the DBT image has been pushed to AWS ECR, you need to paste its URI in the [chart_songs_dag.py file](/spotify_dag/chart_songs_dag.py) in the EcsRegisterTaskDefinitionOperator under *image:*

__Create the corresponding Redshift schema__

Within your Redshift cluster, you need to create two schemas in the database spotify_project:
- mart
- stage 

__Upload the spotify_dag folder to EC2__

Once you have created the AWS infrastructure, you need to upload the spotify_dag folder to your ec2 instance in the dag folder. You can do this via scp. 
Before you upload your dag, you have to insert a few parameters. They can be found in lines: 209, 227, 260, 261

Then execute:

scp -r -i <key_file_name.pem> /spotify_dag ubuntu@<ec2_instance_public_ip>:/~/airflow/dags

##  Future outlook
As any project one can always advance it further. Feel free to clone the project and built new features. Pull requests are very much accepted, especially if you are working on the following topics:
- Unit tests 
- Executing the Python script via Aws Lambda 
- Set Github Actions up without using sensitive keys 