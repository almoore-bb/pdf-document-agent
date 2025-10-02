variable "ally_dev_account_id" {
    type = string
    default = "497264373625"
}

variable "collection_name" {
  description = "Name of the OpenSearch Serverless collection."
  default     = "allyopensearchcollection"
}

variable "subnet_id" {
    type = string
    default = "subnet-42ea140b"
}

variable "vpc_id" {
    type = string
    default = "vpc-5d2c5b3a"
}