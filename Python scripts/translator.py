# This translator script is used for the translation experiments in the benchmark creation process.
# It uses the DeepSeek API to translate SPARQL queries into natural language questions.
import requests
import json
import argparse
from typing import Optional
import random
from collections import defaultdict
from tqdm import tqdm

NAMELESS_KEYWORDS = ["terrain", "lake", "swamp"]

class SPARQLTranslator:
    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        """
        Initialize the SPARQL translator with DeepSeek API credentials
        
        Args:
            api_key: Your DeepSeek API key
            model: The DeepSeek model to use ("deepseek-chat" or "deepseek-reasoner")
        """
        self.api_key = api_key
        self.model = model
        self.api_url = "https://api.deepseek.com/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def translate_query(self, sparql_query: str, context: Optional[str] = None) -> str:
        """
        Translate a SPARQL query to natural language using DeepSeek API
        
        Args:
            sparql_query: The SPARQL query to translate
            context: Optional context about the dataset or domain
            
        Returns:
            Natural language translation of the query
        """
        # Construct the prompt
        system_prompt = """You are an expert SPARQL-to-natural language translator. 
        Convert the given SPARQL query into a clear, concise, and accurate natural language question.
        Focus on maintaining the semantic meaning while making it easily understandable. Only return the natural language question"""
        
        user_prompt = f"Translate this SPARQL query to natural language:"
        if context:
            user_prompt += f"\nContext: {context}"
        user_prompt += f"\n\nSPARQL Query:\n{sparql_query}"
        
        # Prepare the API request
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3,  # Lower temperature for more precise translations
            "max_tokens": 500,
            "stream": False
        }
        
        try:
            # Make the API request
            response = requests.post(self.api_url, headers=self.headers, json=data)
            response.raise_for_status()
            
            # Extract and return the translation
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"API request failed: {str(e)}")
        except (KeyError, IndexError) as e:
            raise Exception(f"Failed to parse API response: {str(e)}")



def main():
    parser = argparse.ArgumentParser(
        description="Translate a curated list of SPARQL queries to natural language.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--api-key", 
        required=True, 
        help="Your DeepSeek API key."
    )
    parser.add_argument(
        "--input-file", 
        default="curated_queries_for_translation.json",
        help="The human-approved JSON file from the review script."
    )
    parser.add_argument(
        "--output-file", 
        default="translation_comparison_final.json",
        help="The final JSON file with LLM translation comparisons."
    )
    
    args = parser.parse_args()

    # --- 1. Load the Curated Queries ---
    print(f"Loading curated queries from '{args.input_file}'...")
    try:
        with open(args.input_file, 'r') as f:
            curated_queries = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file not found at '{args.input_file}'.")
        print("Please run the 'review_and_select.py' script first to create this file.")
        return
    except json.JSONDecodeError:
        print(f"Error: The input file '{args.input_file}' is not a valid JSON file.")
        return

    if not curated_queries:
        print("The input file is empty. No queries to translate.")
        return

    print(f"Successfully loaded {len(curated_queries)} curated queries for translation.")

    # --- 2. Initialize Translator and Run Translations ---
    translator = SPARQLTranslator(api_key=args.api_key) 
    results_for_comparison = []
    
    general_context = "This is for a knowledge graph about The Witcher video game franchise and all it's games and expansions."

    print("\nStarting translations...")
    # The loop now directly iterates over the curated list
    for item in tqdm(curated_queries, desc="Translating Queries"):
        sparql_query = item['query']
        template_nlq = item['natural_language_question']

        # --- Method 1: Direct Translation ---
        try:
            direct_translation = translator.translate_query(sparql_query, context=general_context)
        except Exception as e:
            print(f"\nError during direct translation for query {item['query_id']}: {e}")
            direct_translation = f"ERROR: {e}"

        # --- Method 2: Context-Enhanced Translation ---
        enhanced_context = (
            f"{general_context}\n"
            f"The ideal output should be a clear, natural question. "
            f"Use this example as a guide for style and phrasing: '{template_nlq}'"
        )
        try:
            context_enhanced_translation = translator.translate_query(sparql_query, context=enhanced_context)
        except Exception as e:
            print(f"\nError during enhanced translation for query {item['query_id']}: {e}")
            context_enhanced_translation = f"ERROR: {e}"
            
        # Store all versions for comparison
        results_for_comparison.append({
            "query_id": item['query_id'],
            "template_id": item['template_id'],
            "sparql_query": sparql_query,
            "template_generated_nlq": template_nlq,
            "direct_llm_translation": direct_translation,
            "context_enhanced_llm_translation": context_enhanced_translation
        })

    # --- 3. Save Results ---
    print(f"\nAll translations complete. Saving results to '{args.output_file}'...")
    with open(args.output_file, 'w') as f:
        json.dump(results_for_comparison, f, indent=2)
    
    print("Done!")

if __name__ == "__main__":
    main()