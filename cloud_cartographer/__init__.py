#!/usr/bin/env python3
"""Cloud Cartographer.

Main entrypoint module for the ccarto tool.
"""
import argparse
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from concurrent.futures import ThreadPoolExecutor
import functools
from itertools import count
import json
import logging
import time
import yaml

from py_markdown_table.markdown_table import markdown_table


PARSER = argparse.ArgumentParser(description='Cloud Cartographer - AWS CFN Mapping Tool',
                                 prog='ccarto')
PARSER.add_argument("-p", "--profile",
                    help="AWS profile to use")
PARSER.add_argument("-r", "--regions",
                    help="AWS Regions to check",
                    nargs="+",
                    default=[])
PARSER.add_argument("-f", "--filter",
                    help="Tags to filter on, format should be as follows: Key:Value",
                    nargs="+",
                    default=[])
PARSER.add_argument("--headers",
                    help="Output format for markdown table result, string separated",
                    default="StackName,LastUpdatedTime,Tags:owner,Tags:project,Template:Metadata.Build info.built from.origin,Template:Metadata.Build info.built from.file,Template:Metadata.Build info.url,Region")
PARSER.add_argument("-i", "--input",
                    help="Skips json generation and AWS API calls and reads json directly for graph visualization, doesn't output markdown table")
PARSER.add_argument("-o", "--output",
                    help="Filename to output json graph data to",
                    default="cloudformation_map.json")
PARSER.add_argument("-t", "--threads",
                    help="Number of threads to spawn when crawling parsing cloudformation stacks",
                    default=16)
PARSER.add_argument("-v", "--verbose",
                    help="Print more information",
                    action="store_true",
                    default=False)
ARGS = PARSER.parse_args()

logging.basicConfig(level=logging.INFO)
if ARGS.verbose:
    logging.basicConfig(level=logging.DEBUG)

RESOURCE_TYPE_MAPPING = {
    "ApiGatewayV2": "https://icon.icepanel.io/AWS/svg/App-Integration/API-Gateway.svg",
    "ApplicationAutoScaling": "https://icon.icepanel.io/AWS/svg/Compute/Application-Auto-Scaling.svg",
    "CloudWatch": "https://icon.icepanel.io/AWS/svg/Management-Governance/CloudWatch.svg",
    "CloudFront": "https://icon.icepanel.io/AWS/svg/Networking-Content-Delivery/CloudFront.svg",
    "DynamoDB": "https://icon.icepanel.io/AWS/svg/Database/DynamoDB.svg",
    "EC2": "https://icon.icepanel.io/AWS/svg/Compute/EC2.svg",
    "Events": "https://icon.icepanel.io/AWS/svg/App-Integration/EventBridge.svg",
    "IAM": "https://icon.icepanel.io/AWS/svg/Security-Identity-Compliance/IAM-Identity-Center.svg",
    "Lambda": "https://icon.icepanel.io/AWS/svg/Compute/Lambda.svg",
    "Logs": "https://icon.icepanel.io/AWS/svg/Management-Governance/CloudWatch.svg",
    "Route53": "https://icon.icepanel.io/AWS/svg/Management-Governance/CloudWatch.svg",
    "S3": "https://icon.icepanel.io/AWS/svg/Storage/Simple-Storage-Service.svg",
}

GRAPH_NODE_ID_TO_STACK_MAPPING = {}
NODE_ID_COUNTER = count()

def process_stack(client, tags: dict, region: str, include_templates: bool, stack_summary, matching_stacks: list):
    stack_name = stack_summary['StackName']

    # Get stack details to retrieve tags
    stack_details = client.describe_stacks(StackName=stack_name)
    stack_tags = stack_details['Stacks'][0].get('Tags', [])

    # Convert stack tags to a dictionary
    stack_tags_dict = {tag['Key']: tag['Value'] for tag in stack_tags}

    # Check if stack tags match the required tags
    if all(stack_tags_dict.get(k) == v for k, v in tags.items()):
        all_resources = []
        next_token = None
        while True:
            if next_token:
                response = client.list_stack_resources(StackName=stack_name, NextToken=next_token)
            else:
                response = client.list_stack_resources(StackName=stack_name)
            all_resources.extend(response['StackResourceSummaries'])
            next_token = response.get('NextToken')
            if not next_token:
                break
        stack_details['Stacks'][0]['Resources'] = all_resources

        all_imports = {}
        for output in stack_details['Stacks'][0].get("Outputs", []):
            export = output.get("ExportName", None)
            if not export:
                continue
            all_imports[export] = []
            next_token = None
            while True:
                try:
                    if next_token:
                        response = client.list_imports(ExportName=export, NextToken=next_token)
                    else:
                        response = client.list_imports(ExportName=export)
                except ClientError as e:
                    if e.response['Error']['Code'] == 'ValidationError':
                        logging.debug(f"Export '{export}' is not imported by any stack")
                        break
                    else:
                        raise e
                all_imports[export].extend(response['Imports'])
                next_token = response.get('NextToken')
                if not next_token:
                    break
        stack_details['Stacks'][0]['Imports'] = all_imports
        stack_details['Stacks'][0]['Region'] = region

        if include_templates:
            response = client.get_template(StackName=stack_name)
            template_body = response['TemplateBody']
            if isinstance(template_body, str):  # Template may be JSON or YAML
                try:
                    template_dict = json.loads(template_body)
                except json.JSONDecodeError:
                    template_dict = yaml.safe_load(template_body)
            else:
                template_dict = template_body  # Already a dict (e.g., generated inline templates)
            stack_details['Stacks'][0]['Template'] = template_dict

        matching_stacks.append(stack_details['Stacks'][0])
        logging.debug("Found matching stack %s with details '%s'", stack_name, stack_details)


def list_stacks_by_tags(client, tags: dict, region: str, include_templates: bool) -> list:
    """
    List CloudFormation stacks in a given region that match a list of tags.

    :param region: AWS region as a string (e.g., "us-east-1").
    :param tags: A dictionary of tag keys and values to filter stacks (e.g., {"Environment": "Prod"}).
    :return: A list of stack names that match the tags.
    """
    logging.info("Listing stacks in region '%s'", region)
    # Get all stacks (exclude deleted or otherwise non-existent stacks)
    paginator = client.get_paginator('list_stacks')
    response_iterator = paginator.paginate(
        StackStatusFilter=[
            "CREATE_COMPLETE", "ROLLBACK_IN_PROGRESS", "ROLLBACK_FAILED", "ROLLBACK_COMPLETE", "DELETE_FAILED",
            "UPDATE_IN_PROGRESS", "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS", "UPDATE_COMPLETE", "UPDATE_FAILED",
            "UPDATE_ROLLBACK_IN_PROGRESS", "UPDATE_ROLLBACK_FAILED", "UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS",
            "UPDATE_ROLLBACK_COMPLETE",
        ]
    )

    matching_stacks = []

    executor = ThreadPoolExecutor(max_workers=int(ARGS.threads), thread_name_prefix="crawler")
    work_list = []

    logging.info("Processing stacks from region: '%s'", region)
    for page in response_iterator:
        work_list.extend([executor.submit(process_stack, client, tags, region, include_templates, stack_summary, matching_stacks) for stack_summary in page['StackSummaries']])

    for future in work_list:
        future.result()
    return matching_stacks


def create_transformation_functions(outputs: list):
    """Create a list of transformation functions depending on the desired output (be it an attribute, nested attribute or template attribute)."""
    transformations = []
    for output in outputs:
        if "Template" in output:
            key = output.split(":")[1]
            transformations.append(lambda s, o=output, k=key: (o, functools.reduce(lambda c, i: c.get(i, "???") if isinstance(c, dict) else "???", k.split("."), s['Template'])))
            continue
        if "Tags:" in output:
            key = output.split(":")[1]
            transformations.append(lambda s, o=output, k=key: (o, next(t['Value'] for t in s.get("Tags") if t['Key'] == k)))
            continue
        transformations.append(lambda s, o=output: (o, s.get(o, "???")))

    return transformations


def create_cfn_node(name: str, graph_data: dict) -> str:
    node_id = f"s{next(NODE_ID_COUNTER)}"
    GRAPH_NODE_ID_TO_STACK_MAPPING[name] = node_id
    graph_data["nodes"].append(
        {"id": node_id, "name": name, "image": "https://icon.icepanel.io/AWS/svg/Management-Governance/CloudFormation.svg", "type": "stack"}
    )
    return node_id


def expand_stack_for_graph(stack, graph_data: dict) -> dict:
    """Transform stack details to json for the stack and its resources."""
    name = stack['StackName']
    node_id = "s?"
    if name not in GRAPH_NODE_ID_TO_STACK_MAPPING:
        node_id = create_cfn_node(name, graph_data)
    else:
        # Node was already created when referenced previously via an import/export relation
        node_id = GRAPH_NODE_ID_TO_STACK_MAPPING[name]

    for resource_id, resource in enumerate(stack['Resources']):
        resource_id = f"{node_id}-r{resource_id}"
        logical_resource_id = resource['LogicalResourceId']
        resource_type = RESOURCE_TYPE_MAPPING.get(resource['ResourceType'].split("::")[1], "https://upload.wikimedia.org/wikipedia/commons/9/93/Amazon_Web_Services_Logo.svg")
        graph_data["nodes"].append(
            {"id": resource_id, "name": logical_resource_id, "image": resource_type, "type": "resource"}
        )
        graph_data["links"].append(
            {"source": resource_id, "target": node_id}
        )

    for export, import_stacks in stack['Imports'].items():
        for import_stack in import_stacks:
            if import_stack not in GRAPH_NODE_ID_TO_STACK_MAPPING:
                imported_stack_node_id = create_cfn_node(import_stack, graph_data)
            else:
                imported_stack_node_id = GRAPH_NODE_ID_TO_STACK_MAPPING[import_stack]
            graph_data["links"].append(
                {"source": imported_stack_node_id, "target": node_id, "label": export}
            )
    return graph_data


def main():
    """Entry point for the application script."""
    tags = {key: value for key, value in map(lambda f: f.split(":"), ARGS.filter)}
    include_template = any(h.startswith("Template:") for h in ARGS.headers.split(","))
    session = boto3.Session(profile_name=ARGS.profile)
    stacks = []

    for region in ARGS.regions:
        start_time = time.time()
        client = session.client('cloudformation', region_name=region, config=Config(retries={'mode': 'adaptive', 'max_attempts': 5}))
        stacks.extend(list_stacks_by_tags(client, tags, region, include_template))
        logging.info("Finished collecting stack info in %s! Elapsed time since start %s", region, time.strftime('%Mm%Ss', time.gmtime(time.time() - start_time)))

    # Sort list by stack name to keep output consistent across runs
    stacks = sorted(stacks, key=lambda d: d['StackName'])

    # For each desired element in the output create a suitable transformation function
    graph_data = {"nodes": [], "links": []}
    transformations = create_transformation_functions(ARGS.headers.split(","))
    table_data = []
    for stack in stacks:
        expand_stack_for_graph(stack, graph_data)
        data = {key: value for transform in transformations for key, value in [transform(stack)]}
        table_data.append(data)

    # Output graph json
    with open(ARGS.output, "w") as outfile:
        outfile.write(json.dumps(graph_data))

    # Output markdown table
    markdown = markdown_table(table_data).set_params(row_sep = 'markdown', quote = False).get_markdown()
    print(markdown)

if __name__ == '__main__':
    main()
