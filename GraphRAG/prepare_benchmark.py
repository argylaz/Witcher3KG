import json
import re

def prepare_witcher_benchmark(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # The templates we want for HippoRAG Relational Reasoning
    target_templates = ["T5", "T6", "T7", "T12", "T14"]
    
    processed_questions = []

    for item in data:
        # Use 'template_id' field
        # Logic: If template_id starts with any of our targets
        if any(item['template_id'].startswith(t) for t in target_templates):
            
            # EXTRACT SEED ENTITIES:
            # HippoRAG needs the URIs mentioned in the question to start the PageRank.
            # Since they are in the SPARQL query inside <...>, we grab them.
            sparql = item['sparql_query']
            # Find all URIs inside angle brackets
            found_uris = re.findall(r'<(http://[^>]+)>', sparql)
            
            # Filter out standard namespaces (geo, rdf, etc) to get only Witcher entities
            seed_entities = [u for u in found_uris if "cgi.di.uoa.gr/witcher" in u]

            processed_questions.append({
                "query_id": item['query_id'],
                "template_id": item['template_id'],
                "question": item['natural_language_question'],
                "sparql_query": sparql,
                "seed_entities": list(set(seed_entities)), # HippoRAG starting nodes
                "answer": None # WE WILL FILL THIS IN THE NEXT STEP
            })

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(processed_questions, f, indent=4, ensure_ascii=False)
    
    print(f"Processed: {input_file}")
    print(f"Kept {len(processed_questions)} out of {len(data)} questions.")

# Run for the thesis sets
prepare_witcher_benchmark("../WitcherBenchmark/validation_set.json", "witcher_val_filtered.json")
prepare_witcher_benchmark("../WitcherBenchmark/test_set.json", "witcher_test_filtered.json")