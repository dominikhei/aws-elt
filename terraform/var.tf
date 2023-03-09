variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-central-1"
}

variable "redshift_user" {
  description = "AWS user name for Redshift"
  type        = string
  default     = ""
}

variable "redshift_password" {
  description = "AWS password for Redshift"
  type        = string
  default     = ""
}

variable "spotify_clientid" {
    description = "The clientID for access to the spotify API"
    type = string
    default = ""
}

variable "spotify_clientsecret" {
    description = "The clientSecret for access to the spotify API"
    type = string
    default = ""
}

variable "my_ip" {
  description = "Your local IP adress"
  type = string
  default = ""
}