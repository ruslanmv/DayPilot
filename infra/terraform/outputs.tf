output "ecr_repositories" {
  description = "ECR repository URLs for CI image publishing."
  value       = { for name, repo in aws_ecr_repository.services : name => repo.repository_url }
}

output "ecs_cluster_name" {
  description = "ECS cluster name for deployment pipelines."
  value       = aws_ecs_cluster.main.name
}

output "private_subnet_ids" {
  description = "Private subnet IDs for ECS and managed databases."
  value       = aws_subnet.private[*].id
}
