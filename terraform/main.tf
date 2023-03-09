provider "aws" {
  region = var.aws_region #replace the region to your desired region in the var.tf file
}

provider "tls" {

}

# Create a .pem key to openssh into the EC2 instance

resource "tls_private_key" "this" {
  algorithm     = "RSA"
  rsa_bits      = 4096
}

resource "aws_key_pair" "this" {
  key_name      = "airflow-server-key"
  public_key    = tls_private_key.this.public_key_openssh

  provisioner "local-exec" {
    command = <<-EOT
      echo "${tls_private_key.this.private_key_pem}" > airflow-server-key.pem
    EOT
  }
}


#Create a VPC in which all services sit in

resource "aws_vpc" "spotify-project-vpc" {
  cidr_block = "10.0.0.0/16"

  tags = {
    Name = "spotify-project-vpc"
  }
}

resource "aws_subnet" "spotify-subnet" {
  vpc_id     = aws_vpc.spotify-project-vpc.id
  cidr_block = "10.0.1.0/24"

  tags = {
    Name = "spotify-subnet"
  }
}

resource "aws_subnet" "spotify-subnet-2" {
  vpc_id     = aws_vpc.spotify-project-vpc.id
  cidr_block = "10.0.2.0/24"

  tags = {
    Name = "spotify-subnet-2"
  }
}

resource "aws_redshift_subnet_group" "redshift-subnet" {
  name       = "redshift-subnet"
  subnet_ids = [aws_subnet.spotify-subnet.id, aws_subnet.spotify-subnet-2.id]
}


# Security group for all services
resource "aws_security_group" "project_security_group" {
  name_prefix = "project-security-group"

 ingress {
    from_port = 0
    to_port   = 65535
    protocol  = "tcp"
    self = true
  }
 ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [ var.my_ip ]
  }
 ingress {
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = [ var.my_ip ]
  }
 egress {
    from_port = 0
    to_port   = 0
    protocol  = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  vpc_id = aws_vpc.spotify-project-vpc.id
}

# Create an internet gateway
resource "aws_internet_gateway" "spotify_internet_gateway" {
  vpc_id = aws_vpc.spotify-project-vpc.id
}

resource "aws_route_table" "spotify_route_table" {
  vpc_id = aws_vpc.spotify-project-vpc.id  

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.spotify_internet_gateway.id
  }
}


# Attach the internet gateway to the VPC's route table
resource "aws_route" "route" {
  route_table_id         = aws_route_table.spotify_route_table.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.spotify_internet_gateway.id
}

resource "aws_route_table_association" "spotify_route_table_association" {
  subnet_id      = aws_subnet.spotify-subnet.id
  route_table_id = aws_route_table.spotify_route_table.id
}



# EC2 instance
resource "aws_instance" "airflow_server" {
  ami           = "ami-0d1ddd83282187d18" 
  instance_type = "t2.medium"
  subnet_id     = aws_subnet.spotify-subnet.id
  key_name= "airflow-server-key"
  associate_public_ip_address = true

  tags = {
    Name = "airflow-server"
  }

  vpc_security_group_ids = [
    aws_security_group.project_security_group.id
  ]

user_data = <<EOF
#!/bin/bash
echo "-------------------------STARTING AIRFLOW SETUP---------------------------"
sudo apt-get -y update
sudo apt-get -y install docker.io docker-compose

sudo chmod 666 /var/run/docker.sock

echo 'Installing and setting up Airflow'
mkdir /home/ubuntu/airflow 
cd /home/ubuntu/airflow
mkdir -p ./dags ./logs ./plugins
curl -LfO 'https://airflow.apache.org/docs/apache-airflow/2.5.1/docker-compose.yaml'
echo -e "AIRFLOW_UID=$(id -u)" > .env

echo 'Starting the Airflow Services, this might take a few minutes"
/usr/bin/docker-compose up airflow-init
/usr/bin/docker-compose up -d

docker exec -it airflow_airflow-scheduler_1 bash 
airflow connections add Spotify_Api_Tokens --conn-type aws --conn-login ${var.spotify_clientid} --conn-password ${var.spotify_clientsecret}
airflow connections add 'aws-iam' --conn-type aws --conn-extra '{"region_name": "${var.aws_region}"}' 
airflow connections add redshift-spotify --conn-type redshift --conn-login ${var.redshift_user} --conn-password ${var.redshift_password} --conn-host ${aws_redshift_cluster.redshift_cluster_spotify.endpoint} --conn-port 5439 
pip3 install soda-core datetime python-dotenv pandas boto3
exit 

echo "-------------------------ENDING AIRFLOW SETUP---------------------------"
EOF

iam_instance_profile = aws_iam_instance_profile.ec2_instance_profile.name
}

resource "aws_iam_instance_profile" "ec2_instance_profile" {
  name = "ec2-instance-profile"

  role = aws_iam_role.ec2_role.name
}

# ECS cluster
resource "aws_ecs_cluster" "dbt_cluster" {
  name = "dbt-cluster"
}

# ECR repository
resource "aws_ecr_repository" "dbt_repository" {
  name = "dbt-models"
}

# Redshift cluster
resource "aws_redshift_cluster" "redshift_cluster_spotify" {
  cluster_identifier      = "redshift-cluster-spotify"
  node_type               = "dc2.large"
  database_name = "spotify_project"
  master_username         = var.redshift_user
  master_password         = var.redshift_password
  cluster_subnet_group_name = aws_redshift_subnet_group.redshift-subnet.name
  skip_final_snapshot = true
  publicly_accessible = false
  tags = {
    Name = "redshift-cluster-spotify"
  }
  vpc_security_group_ids = [
    aws_security_group.project_security_group.id
  ]
}

resource "aws_redshift_cluster_iam_roles" "redshift_role" {
  cluster_identifier = aws_redshift_cluster.redshift_cluster_spotify.cluster_identifier
  iam_role_arns      = [aws_iam_role.redshift_role.arn]
}

# S3 bucket
resource "aws_s3_bucket" "spotify_project1" {
  bucket = "spotify-project1"

  tags = {
    Name = "spotify-project1"
  }
}

# IAM roles and policies
resource "aws_iam_role" "ec2_role" {
  name = "ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = ["ec2.amazonaws.com", "ecs.amazonaws.com", "ecs-tasks.amazonaws.com"]
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
  managed_policy_arns = ["arn:aws:iam::aws:policy/AmazonS3FullAccess", "arn:aws:iam::aws:policy/AmazonEC2FullAccess", "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryFullAccess", "arn:aws:iam::aws:policy/AmazonRedshiftFullAccess", "arn:aws:iam::aws:policy/AmazonECS_FullAccess", ""]
}

resource "aws_iam_policy" "ec2_spotify_iam_policy" {
  name        = "ec2_spotify_iam_policy"
  policy      = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = [
          "iam:ListRoles",
          "iam:GetRole",
          "iam:PassRole",
        ]
        Effect   = "Allow"
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ec2_role_attachment7" {
  policy_arn = aws_iam_policy.ec2_spotify_iam_policy.arn
  role       = aws_iam_role.ec2_role.name
}

resource "aws_iam_role" "redshift_role" {
name = "redshift-role"

assume_role_policy = jsonencode({
Version = "2012-10-17"
Statement = [
{
Effect = "Allow"
Principal = {
Service = "redshift.amazonaws.com"
}
Action = "sts:AssumeRole"
}
]
})
managed_policy_arns = ["arn:aws:iam::aws:policy/AmazonS3FullAccess", "arn:aws:iam::aws:policy/AmazonRedshiftFullAccess"]
}

#Create an ECR user with access keys to have access to ECR from Github actions:

resource "aws_iam_user" "ecr_user" {
  name = "ecr_user"
}

resource "aws_iam_user_policy_attachment" "ecr_user_policy" {
  user       = aws_iam_user.ecr_user.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryFullAccess"
}

