# translate_final_sets.py

import json
import argparse
from tqdm import tqdm

# Import the SPARQLTranslator from translator.py
try:
    from translator import SPARQLTranslator
except ImportError:
    print("Error: Could not find 'translator.py'.")
    print("Please make sure your SPARQLTranslator script is in the same directory.")
    exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Enrich final benchmark sets with context-enhanced LLM translations.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--api-key", required=True, help="DeepSeek API key.")
    parser.add_argument("--validation-file", default="validation_set.json", help="The validation set to process.")
    parser.add_argument("--test-file", default="test_set.json", help="The test set to process.")
    parser.add_argument("--translated-file", default="translation_comparison_final.json", help="The file with our ~50 already-translated queries.")
    parser.add_argument("--full-benchmark-file", default="witcher_benchmark_dataset_final_v7.json", help="The original large benchmark file, needed for context.")
    
    args = parser.parse_args()

    # --- 1. Load All Data and Create Caches ---
    print("Loading all necessary data files...")
    try:
        with open(args.validation_file, 'r') as f:
            validation_set = json.load(f)
        with open(args.test_file, 'r') as f:
            test_set = json.load(f)
        with open(args.translated_file, 'r') as f:
            translated_queries = json.load(f)
        with open(args.full_benchmark_file, 'r') as f:
            all_queries = json.load(f)
    except FileNotFoundError as e:
        print(f"Error: A required file was not found: {e.filename}")
        return

    # Create a cache of already-translated queries for efficiency
    translated_cache = {
        item['query_id']: item['context_enhanced_llm_translation']
        for item in translated_queries
    }
    print(f"Created a cache of {len(translated_cache)} existing translations.")

    # Create a cache of the original template-NLQs for context
    context_cache = {
        item['query_id']: item.get('natural_language_question', '')
        for item in all_queries
    }
    print(f"Created a context cache of {len(context_cache)} template questions.")

    # --- 2. Initialize Translator ---
    translator = SPARQLTranslator(api_key=args.api_key)
    general_context = "This is for a knowledge graph about The Witcher video game franchise and all it's games and expansions."

    # --- 3. Define the Processing Function ---
    def process_set(dataset, desc):
        new_set = []
        for item in tqdm(dataset, desc=desc):
            query_id = item['query_id']
            sparql_query = item['sparql_query']
            final_nlq = "N/A"

            # Case A: The query is already translated. Use the cached version.
            if query_id in translated_cache:
                final_nlq = translated_cache[query_id]
            
            # Case B: The query is new and needs translation.
            else:
                context_nlq = context_cache.get(query_id)
                if not context_nlq:
                    print(f"Warning: Could not find context for new query {query_id}. Using direct translation.")
                    enhanced_context = general_context
                else:
                    enhanced_context = (
                        f"{general_context}\n"
                        f"The ideal output should be a clear, natural question. "
                        f"Use this example as a guide for style and phrasing: '{context_nlq}'"
                    )
                
                try:
                    final_nlq = translator.translate_query(sparql_query, context=enhanced_context)
                except Exception as e:
                    print(f"\nError during translation for query {query_id}: {e}")
                    final_nlq = f"ERROR: {e}"
            
            # Create the new, enriched item for the final dataset
            new_item = item.copy()
            new_item['natural_language_question'] = final_nlq
            new_set.append(new_item)
            
        return new_set

    # --- 4. Process Both Sets ---
    print("\nProcessing Validation Set...")
    final_validation_set = process_set(validation_set, "Translating Validation Set")

    print("\nProcessing Test Set...")
    final_test_set = process_set(test_set, "Translating Test Set")

    # --- 5. Save the Final Sets ---
    val_output_file = "validation_set_with_nlq.json"
    test_output_file = "test_set_with_nlq.json"

    print(f"\nAll translations complete. Saving results...")
    with open(val_output_file, 'w') as f:
        json.dump(final_validation_set, f, indent=2)
    print(f"Saved final validation set to '{val_output_file}'")
    
    with open(test_output_file, 'w') as f:
        json.dump(final_test_set, f, indent=2)
    print(f"Saved final test set to '{test_output_file}'")
    
    print("\nBenchmark creation is complete.")

if __name__ == "__main__":
    main()