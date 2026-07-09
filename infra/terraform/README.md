# Terraform

This folder contains an AWS bootstrap scaffold for production DayPilot deployments:

- ECR repositories for each service image.
- A VPC and two private subnets.
- Internal service security group.
- CloudWatch log groups.
- ECS cluster with container insights.

```bash
cd infra/terraform
terraform init
terraform plan
```

The files are intentionally conservative and do not create public ingress or managed databases until environment-specific networking and compliance requirements are defined.
