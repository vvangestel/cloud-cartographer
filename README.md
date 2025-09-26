# Cloud Cartographer

Cloud Cartographer is a powerful tool for analyzing and visualizing AWS CloudFormation stacks. It provides capabilities to scan your AWS infrastructure, filter stacks by tags, and generate both tabular (markdown) and interactive visualizations of your cloud architecture.

## Features

- **Stack Discovery**: Scan AWS CloudFormation stacks across multiple regions
- **Tag-based Filtering**: Filter stacks based on specific tags
- **Flexible Output**: Generate markdown tables with customizable headers
- **Interactive Visualization**: Create interactive D3.js-based visualizations of stack relationships
- **Import/Export Mapping**: Visualize dependencies between stacks through their import/export relations
- **Multi-region Support**: Analyze stacks across multiple AWS regions

## Installation

### Prerequisites

- Python 3.x
- AWS credentials configured
- Git

### Steps

1. Clone the repository:
```bash
git clone https://github.com/vvangestel/cloud-cartographer.git
cd cloud-cartographer
```

2. Install the package:
```bash
pip3 install .
```

Note: PyPI installation will be available in future releases.

## Usage

### Basic Usage

The basic command structure is:
```bash
ccarto [-h] [-p PROFILE] [-r REGIONS [REGIONS ...]] [-f FILTER [FILTER ...]] [--headers HEADERS] [-i INPUT]
       [-j JSON] [-o OUTPUT] [-v]
```

### Command Line Options

- `-p, --profile PROFILE`: Specify the AWS profile to use
- `-r, --regions REGIONS [REGIONS ...]`: Specify one or more AWS regions to scan
- `-f, --filter FILTER [FILTER ...]`: Filter stacks by tags (format: Key:Value1,Value2,Value3,...)
- `--headers HEADERS`: Custom headers for markdown table output
- `-i, --input INPUT`: Skip AWS API calls and use existing JSON data for visualization
- `-j, --json JSON`: Specify output filename for JSON graph data (defaults to `cloudformation_map.json`)
- `-o, --output OUTPUT`: Specify output filename for README file (defaults to `README.md`)
- `-t, --title TITLE`: Specify title of generated markdown document (defaults to `Cloud Cartographer Table`)
- `-v, --verbose`: Enable verbose output

### Examples

1. Scan all stacks in a specific region:
```bash
ccarto -r eu-west-1
```

2. Filter stacks by tags:
```bash
ccarto -f Environment:Production Team:DevOps
```

3. Use a specific AWS profile and output to a specific file:
```bash
ccarto -p myprofile -o specific_output.json
```

4. Generate visualization from existing JSON: (TODO)
```bash
ccarto -i existing_data.json
```

## Visualization

The tool includes a D3.js-based visualization component that creates an interactive map of your CloudFormation stacks. To use the visualization:

1. Generate the JSON output using the tool
2. Open the included HTML file in a web browser
3. Explore the interactive visualization of your stack relationships

## Contributing

This is a WIP project. Contributions are welcome! Please feel free to submit a Pull Request.

## Support

For bugs and feature requests, please create an issue in the GitHub repository.

## Roadmap

- [ ] PyPI package publication
- [ ] Enhanced filtering capabilities
- [ ] Enhanced visualization options
