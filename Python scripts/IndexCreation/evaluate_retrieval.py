import json
import argparse
import re
import math
from tqdm import tqdm
from collections import defaultdict
from llama_index.core import load_index_from_storage, StorageContext, Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
import warnings

warnings.filterwarnings("ignore", category=FutureWarning, module="sentence_transformers.SentenceTransformer")

def extract_and_categorize_ground_truth(sparql_query, uri_to_type_map):
    """
    Parses a SPARQL query with smarter regex to correctly identify the role
    of each URI (entity, class, or property).
    """
    categorized_uris = defaultdict(set)
    base_uri_pattern = "http://cgi.di.uoa.gr/witcher/"

    # Pattern 1: Find classes (URIs that follow `a` or `rdf:type`)
    class_uris = re.findall(r'\s+a\s+<(' + base_uri_pattern + r'[^>]+)>', sparql_query)
    for uri in class_uris:
        if uri_to_type_map.get(uri) == 'class':
            categorized_uris['class'].add(uri)

    # Pattern 2: Find properties (URIs in the predicate position)
    # This new, simpler pattern looks for subject <URI> object.
    prop_uris = re.findall(r'[\?\w\s<][\w:]+\s+<(' + base_uri_pattern + r'[^>]+)>\s+[\?\w"<\.]', sparql_query)
    for uri in prop_uris:
        if uri_to_type_map.get(uri) == 'property':
            categorized_uris['property'].add(uri)

    # Pattern 3: Find all other URIs and assume they are entities
    all_uris = re.findall(r'<(' + base_uri_pattern + r'[^>]+)>', sparql_query)
    for uri in all_uris:
        # If we haven't already classified it, and it's a resource, it's an entity.
        if 'resource' in uri and uri not in categorized_uris['class'] and uri not in categorized_uris['property']:
             categorized_uris['entity'].add(uri)
    
    return categorized_uris

def calculate_all_metrics_at_k(retrieved_names, ground_truth_names, k):
    """
    Calculates all key retrieval metrics for a single query at a specific k.
    This function now correctly receives an ordered list of retrieved names.
    """
    if not ground_truth_names:
        precision = 1.0 if not retrieved_names else 0.0
        return {'precision': precision, 'recall': 1.0, 'f1': 0.0, 'mrr': 0.0}

    retrieved_k_names = retrieved_names[:k]
    retrieved_set = set(retrieved_k_names)
    ground_truth_set = set(ground_truth_names)
    
    true_positives = retrieved_set.intersection(ground_truth_set)
    
    precision = len(true_positives) / k if k > 0 else 0
    recall = len(true_positives) / len(ground_truth_set)
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

    reciprocal_rank = 0.0
    for i, name in enumerate(retrieved_k_names):
        rank = i + 1
        if name in ground_truth_set:
            reciprocal_rank = 1.0 / rank
            break
            
    return {'precision': precision, 'recall': recall, 'f1': f1, 'mrr': reciprocal_rank}



def main():
    print("=== Starting Retrieval Evaluation Script ===")
    parser = argparse.ArgumentParser(description="Evaluate retrieval performance across different k values.")
    parser.add_argument("--validation-file", default="../WitcherBenchmark/test_set.json", help="The validation set to evaluate against.")
    args = parser.parse_args()

    # --- 1. Setup LlamaIndex & Load Indexes ---
    print("--- Setting up LlamaIndex embedding model ---")
    Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-large-en-v1.5")
    Settings.llm = None
    print("--- Loading indexes from storage ---")
    try:
        entity_index = load_index_from_storage(StorageContext.from_defaults(persist_dir="./storage/entity_index"))
        class_index = load_index_from_storage(StorageContext.from_defaults(persist_dir="./storage/class_index"))
        prop_index = load_index_from_storage(StorageContext.from_defaults(persist_dir="./storage/prop_index"))
    except FileNotFoundError:
        print("Error: Could not load indexes. Please run 'build_indexes.py' first.")
        return

    # --- 2. Create URI-to-Type Lookup Map ---
    print("--- Building URI-to-Type lookup map ---")
    uri_to_type_map = {}
    all_docs = {}
    for doc in entity_index.docstore.docs.values():
        uri_to_type_map[doc.metadata['uri']] = 'entity'
        all_docs[doc.metadata['uri']] = doc
    for doc in class_index.docstore.docs.values():
        uri_to_type_map[doc.metadata['uri']] = 'class'
        all_docs[doc.metadata['uri']] = doc
    for doc in prop_index.docstore.docs.values():
        uri_to_type_map[doc.metadata['uri']] = 'property'
        all_docs[doc.metadata['uri']] = doc
    print(f"Lookup map created with {len(uri_to_type_map)} entries.")

    # --- 3. Load Validation Set ---
    print(f"--- Loading validation set from '{args.validation_file}' ---")
    with open(args.validation_file, 'r') as f:
        validation_set = json.load(f)
    
    # --- 4. K-Sweep Evaluation Loop ---
    k_values_to_test = [10]
    sweep_results = {"k_values": k_values_to_test, "metrics": defaultdict(lambda: defaultdict(list))}

    for k in k_values_to_test:
        print(f"\n--- Running evaluation for k={k} ---")
        
        entity_retriever = entity_index.as_retriever(similarity_top_k=k)
        class_retriever = class_index.as_retriever(similarity_top_k=k)
        prop_retriever = prop_index.as_retriever(similarity_top_k=k)
        
        # This dict will hold scores ONLY from relevant queries
        current_k_metrics = defaultdict(lambda: defaultdict(list))
        
        for item in tqdm(validation_set, desc=f"Evaluating @k={k}"):
            nlq = item['natural_language_question']
            sparql = item['sparql_query']
            
            categorized_gt_uris = extract_and_categorize_ground_truth(sparql, uri_to_type_map)
            
            # We still retrieve for all, as a router would not have this ground truth
            entity_results = [node.metadata.get('uri') for node in entity_retriever.retrieve(nlq)]
            class_results = [node.metadata.get('uri') for node in class_retriever.retrieve(nlq)]
            prop_results = [node.metadata.get('uri') for node in prop_retriever.retrieve(nlq)]

            retrieved_uris = {
                'entity': entity_results, 'class': class_results, 'property': prop_results
            }

            # We only calculate and append metrics for an index if the query was relevant to it.
            for index_name in ['entity', 'class', 'property']:
                gt_for_index = categorized_gt_uris.get(index_name)
                
                # Only proceed if there's a ground truth for this index on this query
                if gt_for_index:
                    metrics = calculate_all_metrics_at_k(retrieved_uris[index_name], gt_for_index, k)
                    
                    for key, value in metrics.items():
                        current_k_metrics[index_name][key].append(value)

        # Average the scores for the current k. This is now a true average over relevant queries.
        for index_name in ['entity', 'class', 'property']:
            # Handle the case where an index had ZERO relevant queries in the entire set
            if not current_k_metrics[index_name]:
                print(f"  - No relevant queries found for {index_name.capitalize()} Index in this run.")
                for metric in ['precision', 'recall', 'f1', 'mrr']:
                     sweep_results["metrics"][index_name][metric].append(0.0)
                continue

            for metric, scores in current_k_metrics[index_name].items():
                avg_score = sum(scores) / len(scores) if scores else 0
                sweep_results["metrics"][index_name][metric].append(avg_score)

    # --- 5. Save and Report Results ---
    print("\n--- Retrieval Evaluation Summary ---")
    print(json.dumps(sweep_results, indent=2))
    
    with open("retrieval_k_sweep_results2.json", 'w') as f:
        json.dump(sweep_results, f, indent=2)
    print("\nMetrics sweep results saved to retrieval_k_sweep_results.json")
