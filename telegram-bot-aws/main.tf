provider "aws" {
  region = var.aws_region
}

# Security Group for Telegram bot (SSH + optional HTTP if needed)
resource "aws_security_group" "bot_sg" {
  name        = "telegram-bot-sg"
  description = "Allow SSH and bot ports"
  
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # Open SSH (you can restrict later)
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# EC2 instance
resource "aws_instance" "bot_instance" {
  ami           = "ami-0c02fb55956c7d316" # Amazon Linux 2 (replace if needed)
  instance_type = var.instance_type
  key_name      = var.key_name
  security_groups = [aws_security_group.bot_sg.name]

  # Provision your bot automatically
  user_data = <<-EOF
              #!/bin/bash
              yum update -y
              amazon-linux-extras install python3 -y
              python3 -m venv /home/ec2-user/bot-venv
              source /home/ec2-user/bot-venv/bin/activate
              pip install --upgrade pip
              pip install python-telegram-bot python-dotenv
              # Copy bot files manually later or use S3
              EOF

  tags = {
    Name = "TelegramBot"
  }
}

# Output the public IP
output "bot_public_ip" {
  value = aws_instance.bot_instance.public_ip
}