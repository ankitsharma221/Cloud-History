# ── Terraform Setup for AWS Mumbai (ap-south-1) ───────────
# Creates 4 lightweight, Free-Tier eligible test resources for live validation.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  description = "AWS Region to deploy test resources"
  type        = string
  default     = "ap-south-1" # Mumbai
}

# 1. Fetch latest Amazon Linux 2023 AMI in Mumbai (ap-south-1)
data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# 2. Default VPC lookup
data "aws_vpc" "default" {
  default = true
}

# ── Resource 1: Production Payment API Instance (Active & Managed) ──
resource "aws_security_group" "payment_sg" {
  name        = "payment-api-sg-test"
  description = "Security group for payment API"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTPS from VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.default.cidr_block]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "payment-api-sg-test"
    Environment = "production"
    ManagedBy   = "Terraform"
  }
}

resource "aws_instance" "payment_api" {
  ami           = data.aws_ami.amazon_linux_2023.id
  instance_type = "t3.micro" # Free tier eligible in ap-south-1 (or t2.micro)
  vpc_security_group_ids = [aws_security_group.payment_sg.id]

  tags = {
    Name        = "payment-api-prod"
    Environment = "production"
    Team        = "Payments Platform"
    Owner       = "payments-team@company.com"
    ManagedBy   = "Terraform"
  }
}

# ── Resource 2: Old Analytics Instance (Candidate for cleanup) ──
resource "aws_instance" "old_analytics" {
  ami           = data.aws_ami.amazon_linux_2023.id
  instance_type = "t3.micro"

  tags = {
    Name    = "old-analytics-server"
    Project = "Analytics-Old"
  }
}

# ── Resource 3: Orphaned EBS Volume (Unattached 1 GB test volume) ──
resource "aws_ebs_volume" "orphaned_volume" {
  availability_zone = aws_instance.payment_api.availability_zone
  size              = 1 # 1 GB
  type              = "gp3"

  tags = {
    Name   = "vol-orphaned-001"
    Backup = "temp-test-backup"
  }
}

# ── Resource 4: Legacy Open Security Group ──
resource "aws_security_group" "legacy_open_sg" {
  name        = "sg-legacy-open-test"
  description = "Legacy open security group for testing drift"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "Open SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "sg-legacy-open-test"
  }
}

# ── Outputs ──
output "payment_api_instance_id" {
  value = aws_instance.payment_api.id
}

output "old_analytics_instance_id" {
  value = aws_instance.old_analytics.id
}

output "orphaned_volume_id" {
  value = aws_ebs_volume.orphaned_volume.id
}

output "legacy_sg_id" {
  value = aws_security_group.legacy_open_sg.id
}
