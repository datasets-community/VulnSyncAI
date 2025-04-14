import os
import argparse
import yaml
import psutil
import asyncio
import time
from datetime import datetime
from processing.data_preprocessor import DataPreprocessor
from data_sources.load_data_source import load_data_sources
from processing.load_normalizer import load_normalizers
from categorization.categorizer import Categorizer
from output.load_exporter import load_exporters
from huggingface_hub import login, HfApi

def get_provider(provider_name):
    for model_info in MODELS_TO_EVALUATE:
        if model_info.get("provider") == provider_name:
            return {
                "model": model_info.get("model"),
                "api_key": model_info.get("api_key"),
                "site": model_info.get("site"),
                "type": model_info.get("type"),
                "config": model_info.get("config")
            }
    return None

def get_data_source(data_source_name):
    for source_info in DATA_SOURCES:
        if source_info.get("name") == data_source_name:
            return {
                "name": source_info.get("name"),
                "api_key": source_info.get("api_key", None)
            }
    return None

# Load configuration
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    with open(config_path, 'r') as file:
        return yaml.safe_load(file)

config = load_config()

MODELS_TO_EVALUATE = config['models_to_evaluate']
DATA_SOURCES = config['data_sources']

async def collect_data(search_params, sources, config):
    """
    Collect vulnerability data from specified sources.
    """
    data_sources = load_data_sources(config)
    print(f"Loaded data sources: {list(data_sources.keys())}")
    vulnerabilities = []

    if 'both' in sources:
        print("Collecting data from both sources")
        tasks = [data_sources[ds_name].collect_data(search_params) for ds_name in data_sources]
        results = await asyncio.gather(*tasks)
        for result in results:
            vulnerabilities.extend(result)
    else:
        for source in sources:
            if source in data_sources:
                print(f"Collecting data from source: {source}")
                vulnerabilities.extend(await data_sources[source].collect_data(search_params))
            else:
                print(f"Unsupported data source: {source}")

    # Debug output
    print(f"Total vulnerabilities collected: {len(vulnerabilities)}")
    print("Sources breakdown:")
    for ds_name in data_sources:
        count = sum(1 for v in vulnerabilities if v.get('source') == ds_name)
        print(f"- {ds_name.capitalize()}: {count}")

    return vulnerabilities

def read_search_params_from_file(file_path):
    with open(file_path, 'r') as file:
        return [line.strip() for line in file.readlines()]

async def main():
    parser = argparse.ArgumentParser(
        description="VulnBuilderAI: Build a vulnerability dataset for systems using an AI provider for categorization",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Load configuration to dynamically add data source choices
    config = load_config()


    try:
        hf_api_key = config['models_to_evaluate'][0].get('HUGGINGFACE_API_KEY')
        if hf_api_key:  # Verifica se a API key do Hugging Face foi fornecida
            api = HfApi()
            user = api.whoami()
            print(f"Logged in as {user['name']}")
        else:
            print("Hugging Face API key not provided. Skipping login.")
    except Exception as e:
        print("Error during Hugging Face login:", e)


    data_source_choices = config['data_sources'] + ['both']

    data_source_choices = [source['name'] for source in config['data_sources']] + ['both']
    
    export_format_choices = config['exporters']

    parser.add_argument('--data-source', choices=data_source_choices, nargs='+', required=True,
                        help="Select the data source(s) for vulnerabilities")  
    parser.add_argument('--gemini-key', help="API key for Gemini")
    parser.add_argument('--chatgpt-key', help="API key for ChatGPT")
    parser.add_argument('--llama-key', help="API key for Llama")
    parser.add_argument('--provider', default=["none"], nargs='*', help="Select if you want to use a LLM (IA) provider or not ")  # Add new argument for Default LLM
    parser.add_argument('--vulners-key', help="API key for Vulners")
    parser.add_argument('--new-source-key', help="API key for New Source")  # Add new source key argument
    parser.add_argument('--export-format', choices=export_format_choices, required=True, help="Export format")
    parser.add_argument('--output-file', default="dataset/dataset_vulnerabilities_AI.csv", help="Output file name")
    parser.add_argument('--search-params', nargs='*', help="Search parameters for vulnerabilities")
    parser.add_argument('--search-file', help="Path to a file containing search parameters")
    args = parser.parse_args()


    search_params = args.search_params or []
    if args.search_file:
        search_params.extend(read_search_params_from_file(args.search_file))

    if not search_params:
        print("No search parameters provided.")
        return

    # Create the output directory if it doesn't exist
    output_dir = os.path.dirname(args.output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Set API keys for data sources
    for source in config['data_sources']:
        if 'api_key' in source:
            os.environ[f"{source['name'].upper()}_API_KEY"] = source['api_key']

    # Start measuring time and resources
    start_time = time.time()
    start_datetime = datetime.now()
    print(f"Program started at: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
    process = psutil.Process(os.getpid())
    start_memory = process.memory_info().rss

    # Load data sources
    data_sources = load_data_sources(config)
    selected_data_sources = {source['name']: data_sources[source['name']] for source in config['data_sources'] if source['name'] in data_sources}

    print("Collecting vulnerability data...")
    vulnerabilities = await collect_data(search_params, args.data_source, config)
    
    if not vulnerabilities:
        print("No vulnerability data collected.")
        return
    
    # Load normalizers
    normalizers = load_normalizers(config)

    print("Preprocessing data...")
    data_preprocessor = DataPreprocessor(normalizers)
    normalized_data = []
    for source_name in selected_data_sources:
        source = selected_data_sources[source_name]
        normalized_data.extend(data_preprocessor.preprocess_data(vulnerabilities, search_params, source, source_name))
    
    if not normalized_data:
        print("No normalized vulnerabilities found.")
        return

    categorized_data = {provider: [] for provider in args.provider}
    categorizer_obj = Categorizer()
    
    skipped_vulnerabilities = 0  # Counter for skipped vulnerabilities


    for provider in args.provider:
        provider_type = get_provider(provider)
        print(f"Vulnerability categorizing {provider}...")
        if provider_type:
          if provider_type["api_key"]:
            os.environ["PROVIDER_API_KEY"] = provider_type["api_key"]
          if provider_type["site"]:
            os.environ["PROVIDER_API_URL"] = provider_type["site"]
          if provider_type["model"]:
            os.environ["PROVIDER_API_MODEL"] = provider_type["model"]
          if provider_type["type"]:
            os.environ["PROVIDER_TYPE"] = provider_type["type"]
          if provider_type["config"]:
            os.environ["PROVIDER_CONFIG"] = provider_type["config"]
            
        for vuln in normalized_data:
            if not vuln.get("id"):
                skipped_vulnerabilities += 1
                continue
            description = vuln.get("description", "")
            result = None
            
            try:
                result = await categorizer_obj.categorize_vulnerability_provider(description)
            except Exception as e:
                print(f"Error categorizing vulnerability with {provider}: {e}")
                result = [{"cwe_category": "UNKNOWN", "explanation": str(e), "cause": "", "impact": ""}]
            
            if result and len(result) > 0:
                categorization = result[0]  # Get first result dictionary
                vuln["cwe_category"] = categorization.get("cwe_category", "UNKNOWN")
                vuln["cwe_explanation"] = categorization.get("explanation", "")
                vuln["cause"] = categorization.get("cause", "")
                vuln["impact"] = categorization.get("impact", "")
                vuln["description_normalized"] = description
                vuln["explanation"] = categorization.get("explanation", "")
            else:
                # Fallback values if categorization fails
                vuln["cwe_category"] = "UNKNOWN"
                vuln["cwe_explanation"] = ""
                vuln["cause"] = ""
                vuln["impact"] = ""
                vuln["description_normalized"] = description
                vuln["explanation"] = ""
                print(f"Warning: No categorization result for vulnerability ID {vuln.get('id')}")
                
            categorized_data[provider].append(vuln)
    
        print(f"Total categorized vulnerabilities for {provider}: {len(categorized_data[provider])}")
        
        if provider == "none":
            output = "dataset/" + args.output_file
        else:
            output = provider + '_dataset/' + args.output_file

        print(f"Exporting data to {output}")
        exporters = load_exporters(config, output)
        if args.export_format not in exporters:
           print(f"Unsupported export format: {args.export_format}")
           return

        print(f"Exporting data to {output}")
        exporter = exporters[args.export_format]
        exporter.export(categorized_data[provider])

        # Log the number of skipped vulnerabilities
        if skipped_vulnerabilities > 0:
            print(f"Total vulnerabilities skipped due to missing ID: {skipped_vulnerabilities}")

        # End measuring time and resources
        end_time = time.time()
        end_datetime = datetime.now()
        print(f"Program ended at: {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        end_memory = process.memory_info().rss
        print("Process completed.")
        print(f"Total execution time: {end_time - start_time:.2f} seconds")
        print(f"Memory used: {(end_memory - start_memory) / (1024 * 1024):.2f} MB")


if __name__ == "__main__":
    asyncio.run(main())