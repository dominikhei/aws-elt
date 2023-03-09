FROM python:3.11-slim

RUN pip3 install dbt-redshift==1.4.0

WORKDIR /dbt_project

COPY spotify /dbt_project/

CMD ["sh", "-c", "dbt deps && dbt run"]