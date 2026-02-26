variable "aws_region" {
  default = "us-east-1"
}

variable "instance_type" {
  default = "t3.micro"
}

variable "key_name" {
  description = "Name of your AWS key pair"
}

variable "bot_folder" {
  default = "./bot"
}