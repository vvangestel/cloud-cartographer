#!/usr/bin/env python3
"""Cloud Cartographer.

Main entrypoint module for the ccarto tool.
"""
import argparse
import boto3
import logging

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
PARSER.add_argument("-o", "--output",
                    help="Output format for markdown table result, string separated",
                    default="StackName,LastUpdatedTime,Tags:owner,Tags:project,Template:Metadata.build info.built from.file,Region")
PARSER.add_argument("-v", "--verbose",
                    help="Print more information",
                    action="store_true",
                    default=False)
ARGS = PARSER.parse_args()

logging.basicConfig(level=logging.INFO)
if ARGS.verbose:
    logging.basicConfig(level=logging.DEBUG)


def list_stacks_by_tags(client, tags: dict, region: str) -> list:
    """
    List CloudFormation stacks in a given region that match a list of tags.

    :param region: AWS region as a string (e.g., "us-east-1").
    :param tags: A dictionary of tag keys and values to filter stacks (e.g., {"Environment": "Prod"}).
    :return: A list of stack names that match the tags.
    """
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

    for page in response_iterator:
        for stack_summary in page['StackSummaries']:
            stack_name = stack_summary['StackName']

            # Get stack details to retrieve tags
            stack_details = client.describe_stacks(StackName=stack_name)
            stack_tags = stack_details['Stacks'][0].get('Tags', [])

            # Convert stack tags to a dictionary
            stack_tags_dict = {tag['Key']: tag['Value'] for tag in stack_tags}

            # Check if stack tags match the required tags
            if all(stack_tags_dict.get(k) == v for k, v in tags.items()):
                stack_details['Stacks'][0]['Region'] = region
                matching_stacks.append(stack_details['Stacks'][0])
                logging.debug("Found matching stack %s with details '%s'", stack_name, stack_details)

    return matching_stacks


def create_transformation_functions(outputs: list):
    """Create a list of transformation functions depending on the desired output (be it an attribute, nested attribute or template attribute)."""
    transformations = []
    for output in outputs:
        if "Template" in output:
            # TODO
            continue
        if "Tags:" in output:
            key = output.split(":")[1]
            transformations.append(lambda s, o=output, k=key: (o, next(t['Value'] for t in s.get("Tags") if t['Key'] == k)))
            continue
        transformations.append(lambda s, o=output: (o, s.get(o, "???")))

    return transformations


def main():
    """Entry point for the application script."""
    tags = {key: value for key, value in map(lambda f: f.split(":"), ARGS.filter)}
    session = boto3.Session(profile_name=ARGS.profile)
    stacks = []
    for region in ARGS.regions:
        client = session.client('cloudformation', region_name=region)
        stacks.extend(list_stacks_by_tags(client, tags, region))

    # Sort list by stack name to keep output consistent across runs
    stacks = sorted(stacks, key=lambda d: d['StackName'])

    # For each desired element in the output create a suitable transformation function
    transformations = create_transformation_functions(ARGS.output.split(","))
    table_data = []
    for stack in stacks:
        data = {key: value for transform in transformations for key, value in [transform(stack)]}
        logging.info(data)
        table_data.append(data)

    # Output markdown table
    markdown = markdown_table(table_data).get_markdown()
    print(markdown)

if __name__ == '__main__':
    main()
