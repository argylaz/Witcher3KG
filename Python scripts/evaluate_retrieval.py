# evaluate_retrieval.py

import json
import argparse
import re
from tqdm import tqdm
from collections import defaultdict
from llama_index.core import load_index_from_storage, StorageContext, Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
import warnings
import math

warnings.filterwarnings("ignore", category=FutureWarning, module="sentence_transformers.SentenceTransformer")

def extract_and_categorize_ground_truth(sparql_query, uri_to_type_map):
    """
    Parses a SPARQL query and categorizes the found URIs into entity, class,
    and property sets based on the pre-built lookup map.
    """
    # Extract URIs from the SPARQL query using this regex pattern
    uris = re.findall(r'<(http://cgi\.di\.uoa\.gr/witcher/.*?/.*?)>', sparql_query)
    
    categorized_uris = defaultdict(set)
    for uri in uris:
        uri_type = uri_to_type_map.get(uri)
        if uri_type:
            categorized_uris[uri_type].add(uri)
            
    return categorized_uris


def calculate_mrr(retrieved_items, ground_truth_names):
    """Reciprocal Rank."""
    for i, item in enumerate(retrieved_items):
        rank = i + 1
        retrieved_name = item.metadata.get('name', '')
        if retrieved_name in ground_truth_names:
            return 1.0 / rank
    return 0.0


def calculate_hits_at_k(retrieved_items, ground_truth_names, k):
    """Hits@k (Recall@k): 1 if any relevant item is in top-k, else 0."""
    for item in retrieved_items[:k]:
        if item.metadata.get('name', '') in ground_truth_names:
            return 1.0
    return 0.0


def calculate_precision_at_k(retrieved_items, ground_truth_names, k):
    """Precision@k: relevant retrieved / k."""
    retrieved_k = [item.metadata.get('name', '') for item in retrieved_items[:k]]
    correct = sum(1 for name in retrieved_k if name in ground_truth_names)
    return correct / k if k > 0 else 0.0


def calculate_recall_at_k(retrieved_items, ground_truth_names, k):
    """Recall@k: relevant retrieved / total relevant."""
    if not ground_truth_names:
        return 0.0
    retrieved_k = [item.metadata.get('name', '') for item in retrieved_items[:k]]
    correct = sum(1 for name in retrieved_k if name in ground_truth_names)
    return correct / len(ground_truth_names)


def calculate_f1_at_k(retrieved_items, ground_truth_names, k):
    """F1@k: harmonic mean of precision@k and recall@k."""
    precision = calculate_precision_at_k(retrieved_items, ground_truth_names, k)
    recall = calculate_recall_at_k(retrieved_items, ground_truth_names, k)
    if precision + recall == 0:
        return 0.0
    return 2 * (precision * recall) / (precision + recall)


def calculate_ndcg_at_k(retrieved_items, ground_truth_names, k):
    """nDCG@k: Normalized Discounted Cumulative Gain."""
    dcg = 0.0
    for i, item in enumerate(retrieved_items[:k]):
        rank = i + 1
        if item.metadata.get('name', '') in ground_truth_names:
            dcg += 1.0 / math.log2(rank + 1)

    # Ideal DCG (best possible ranking)
    ideal_hits = min(len(ground_truth_names), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))

    return dcg / idcg if idcg > 0 else 0.0


# USED BY THE FAILURE ANALYSIS MAIN
def calculate_metrics(retrieved_uris, ground_truth_uris):
    """

    Calculates Precision, Recall, F1, and Reciprocal Rank for a single query.
    Takes lists of URIs as input.
    """
    if not ground_truth_uris:
        # If there's nothing to find, it's a perfect score by default.
        return {'precision': 1.0, 'recall': 1.0, 'f1': 1.0, 'rr': 0.0}

    # Use sets for efficient intersection
    retrieved_set = set(retrieved_uris)
    ground_truth_set = set(ground_truth_uris)
    
    true_positives = retrieved_set.intersection(ground_truth_set)
    
    precision = len(true_positives) / len(retrieved_set) if retrieved_set else 0
    recall = len(true_positives) / len(ground_truth_set)
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

    # Calculate Reciprocal Rank
    reciprocal_rank = 0.0
    for i, uri in enumerate(retrieved_uris):
        rank = i + 1
        if uri in ground_truth_set:
            reciprocal_rank = 1.0 / rank
            break # Found the first correct item
            
    return {'precision': precision, 'recall': recall, 'f1': f1, 'rr': reciprocal_rank}




# THIS MAIN IS FOR EVALUATING AGAINST A VALIDATION SET AND LOGGING FAILURES

def main():
    parser = argparse.ArgumentParser(description="Evaluate retrieval performance with per-index failure analysis.")
    parser.add_argument("--validation-file", default="../WitcherBenchmark/test_set.json", help="The validation set to evaluate against.")
    parser.add_argument("--top-k", type=int, default=10, help="The number of results to retrieve for evaluation.")
    args = parser.parse_args()

    # --- 1. Setup LlamaIndex ---
    print("--- Setting up LlamaIndex embedding model ---")
    Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-large-en-v1.5")
    Settings.llm = None

    # --- 2. Load Indexes and Create Retrievers ---
    print("--- Loading indexes from storage ---")
    try:
        entity_index = load_index_from_storage(StorageContext.from_defaults(persist_dir="./storage/entity_index"))
        class_index = load_index_from_storage(StorageContext.from_defaults(persist_dir="./storage/class_index"))
        prop_index = load_index_from_storage(StorageContext.from_defaults(persist_dir="./storage/prop_index"))
    except FileNotFoundError:
        print("Error: Could not load indexes. Please run 'build_indexes.py' first.")
        return

    entity_retriever = entity_index.as_retriever(similarity_top_k=args.top_k)
    class_retriever = class_index.as_retriever(similarity_top_k=args.top_k)
    prop_retriever = prop_index.as_retriever(similarity_top_k=args.top_k)

    # --- 3. Create a master lookup map of all URIs to their index type ---
    print("--- Building URI-to-Type lookup map ---")
    uri_to_type_map = {}
    for doc in entity_index.docstore.docs.values():
        uri_to_type_map[doc.metadata['uri']] = 'entity'
    for doc in class_index.docstore.docs.values():
        uri_to_type_map[doc.metadata['uri']] = 'class'
    for doc in prop_index.docstore.docs.values():
        uri_to_type_map[doc.metadata['uri']] = 'property'
    print(f"Lookup map created with {len(uri_to_type_map)} entries.")

    # --- 4. Load Validation Set ---
    print(f"--- Loading validation set from '{args.validation_file}' ---")
    with open(args.validation_file, 'r') as f:
        validation_set = json.load(f)
     
    # --- 5. Run Evaluation Loop with Per-Index Ground Truth ---
    all_metrics = defaultdict(lambda: defaultdict(list))
    retrieval_failures = defaultdict(list)

    for item in tqdm(validation_set, desc="Evaluating Retrieval"):
        nlq = item['natural_language_question']
        sparql = item['sparql_query']
        
        # Categorize all ground truth URIs found in the SPARQL query
        categorized_gt_uris = extract_and_categorize_ground_truth(sparql, uri_to_type_map)
        
        if not categorized_gt_uris:
            continue

        # Retrieve from each index
        entity_results = entity_retriever.retrieve(nlq)
        class_results = class_retriever.retrieve(nlq)
        prop_results = prop_retriever.retrieve(nlq)

        retrieved_uris = {
            'entity': [node.metadata.get('uri') for node in entity_results],
            'class': [node.metadata.get('uri') for node in class_results],
            'property': [node.metadata.get('uri') for node in prop_results]
        }

        # Calculate metrics and log failures for each index separately
        for index_name in ['entity', 'class', 'property']:
            gt_for_index = categorized_gt_uris.get(index_name, set()) # Use .get() for safety
            
            # The calculation is now always performed.
            # If gt_for_index is empty, calculate_metrics will handle it correctly.
            metrics = calculate_metrics(retrieved_uris[index_name], gt_for_index)
            
            # Store all metrics for averaging
            for key, value in metrics.items():
                all_metrics[index_name][key].append(value)
            
            # We only log a "failure" if there was something to find and we missed it.
            if gt_for_index and metrics['recall'] < 1.0:
                retrieved_set = set(retrieved_uris[index_name])
                missed_uris = gt_for_index - retrieved_set
                retrieval_failures[index_name].append({
                    "query_id": item['query_id'],
                    "question": nlq,
                    "expected_to_find_uris": list(gt_for_index),
                    "actually_retrieved_uris": retrieved_uris[index_name],
                    "missed_uris": list(missed_uris)
                })

    # --- 6. Calculate and Report Final Metrics & Failures ---
    print("\n--- Retrieval Evaluation Summary ---")
    final_metrics = defaultdict(dict)
    for index_name, metric_values in all_metrics.items():
        if metric_values:
            for metric, scores in metric_values.items():
                avg_score = sum(scores) / len(scores) if scores else 0
                final_metrics[index_name][metric] = avg_score
                print(f"  - {index_name.capitalize()} Index Average {metric.upper()}: {avg_score:.4f}")
    
    # Save the main metrics
    with open("retrieval_metrics.json", 'w') as f:
        json.dump(final_metrics, f, indent=2)
    print("\nOverall metrics saved to retrieval_metrics.json")
    
    # Save the detailed, per-index failure report
    if retrieval_failures:
        with open("retrieval_failures_by_index.json", 'w') as f:
            json.dump(retrieval_failures, f, indent=2)
        print(f"\nFound retrieval failures. Detailed report saved to retrieval_failures_by_index.json")
    else:
        print("\nCongratulations! No retrieval failures found.")



# THIS MAIN IS FOR EVALUATING AGAINST A VALIDATION SET AND REPORTING METRICS

# def main():
#     parser = argparse.ArgumentParser(description="Evaluate retrieval performance (MRR, Hits@k, Precision, Recall, F1, nDCG).")
#     parser.add_argument("--validation-file", default="../WitcherBenchmark/validation_set.json", help="Validation set file.")
#     parser.add_argument("--top-k", type=int, default=10, help="Number of results to retrieve.")
#     args = parser.parse_args()

#     # --- 1. Setup LlamaIndex ---
#     print("--- Setting up LlamaIndex embedding model ---")
#     Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-large-en-v1.5")
#     Settings.llm = None

#     # --- 2. Load Indexes ---
#     print("--- Loading indexes from storage ---")
#     try:
#         entity_index = load_index_from_storage(StorageContext.from_defaults(persist_dir="./storage/entity_index"))
#         class_index = load_index_from_storage(StorageContext.from_defaults(persist_dir="./storage/class_index"))
#         prop_index = load_index_from_storage(StorageContext.from_defaults(persist_dir="./storage/prop_index"))
#     except FileNotFoundError:
#         print("Error: Could not load indexes. Please run 'build_indexes.py' first.")
#         return

#     entity_retriever = entity_index.as_retriever(similarity_top_k=args.top_k)
#     class_retriever = class_index.as_retriever(similarity_top_k=args.top_k)
#     prop_retriever = prop_index.as_retriever(similarity_top_k=args.top_k)

#     # --- 3. Load Validation ---
#     print(f"--- Loading validation set from '{args.validation_file}' ---")
#     with open(args.validation_file, 'r') as f:
#         validation_set = json.load(f)
    
#     # --- 4. Run Evaluation ---
#     metrics = defaultdict(lambda: defaultdict(list))
    
#     for item in tqdm(validation_set, desc="Evaluating Retrieval"):
#         nlq = item['natural_language_question']
#         sparql = item['sparql_query']
        
#         ground_truth_names = extract_ground_truth_uris(sparql)
#         if not ground_truth_names:
#             continue

#         # Retrieve results
#         retrieved = {
#             'entity': [node.node for node in entity_retriever.retrieve(nlq)],
#             'class': [node.node for node in class_retriever.retrieve(nlq)],
#             'property': [node.node for node in prop_retriever.retrieve(nlq)],
#         }

#         # Compute metrics
#         for index_name, results in retrieved.items():
#             metrics[index_name]['MRR'].append(calculate_mrr(results, ground_truth_names))
#             metrics[index_name]['Hits@k'].append(calculate_hits_at_k(results, ground_truth_names, args.top_k))
#             metrics[index_name]['Precision@k'].append(calculate_precision_at_k(results, ground_truth_names, args.top_k))
#             metrics[index_name]['Recall@k'].append(calculate_recall_at_k(results, ground_truth_names, args.top_k))
#             metrics[index_name]['F1@k'].append(calculate_f1_at_k(results, ground_truth_names, args.top_k))
#             metrics[index_name]['nDCG@k'].append(calculate_ndcg_at_k(results, ground_truth_names, args.top_k))

#     # --- 5. Report ---
#     print("\n--- Retrieval Evaluation Results ---")
#     final_metrics = {}
#     for index_name, metric_dict in metrics.items():
#         final_metrics[index_name] = {}
#         for metric_name, scores in metric_dict.items():
#             if scores:
#                 avg_score = sum(scores) / len(scores)
#                 final_metrics[index_name][metric_name] = avg_score
#                 print(f"  - {index_name.capitalize()} {metric_name}: {avg_score:.4f}")
#             else:
#                 final_metrics[index_name][metric_name] = None
#                 print(f"  - {index_name.capitalize()} {metric_name}: N/A")

#     with open("retrieval_metrics.json", "w") as f:
#         json.dump(final_metrics, f, indent=2)
#     print("\nMetrics saved to retrieval_metrics.json")



# THIS MAIN IS FOR EVALUATING A SINGLE QUERY AND PRINTING RESULTS

# def main():
#     parser = argparse.ArgumentParser(
#         description="Test information retrieval from specialized LlamaIndex vector indexes.",
#         formatter_class=argparse.RawTextHelpFormatter
#     )
#     parser.add_argument(
#         "query", 
#         type=str, 
#         help="The natural language question to test, enclosed in quotes."
#     )
#     parser.add_argument(
#         "--top-k", 
#         type=int, 
#         default=10,
#         help="The number of top results to retrieve from each index."
#     )
    
#     args = parser.parse_args()

#     # --- 1. Configure LlamaIndex for Retrieval-Only ---
#     print("--- Setting up LlamaIndex embedding model ---")
#     # We only need the embedding model for this task, not a full LLM.
#     try:
#         Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-large-en-v1.5")
#     except Exception as e:
#         print(f"Error initializing embedding model. Is sentence-transformers installed? Error: {e}")
#         return
        
#     Settings.llm = None

#     # --- 2. Load the Persisted Indexes ---
#     print("--- Loading indexes from storage ---")
#     try:
#         entity_index = load_index_from_storage(StorageContext.from_defaults(persist_dir="./storage/entity_index"))
#         class_index = load_index_from_storage(StorageContext.from_defaults(persist_dir="./storage/class_index"))
#         prop_index = load_index_from_storage(StorageContext.from_defaults(persist_dir="./storage/prop_index"))
#     except FileNotFoundError as e:
#         print("Error: Could not load indexes. Did you run 'build_indexes.py' with the enriched data first?")
#         print(f"Details: {e}")
#         return

#     # --- 3. Create a Retriever for each Index ---
#     # A retriever's only job is to find the most similar documents.
#     entity_retriever = entity_index.as_retriever(similarity_top_k=args.top_k)
#     class_retriever = class_index.as_retriever(similarity_top_k=args.top_k)
#     prop_retriever = prop_index.as_retriever(similarity_top_k=args.top_k)

#     # --- 4. Query each Retriever and Display All Results ---
#     print("\n" + "="*50)
#     print(f"Querying with: \"{args.query}\"")
#     print("="*50 + "\n")

#     # Query and display results for each index
#     for name, retriever in [("Entity", entity_retriever), ("Class", class_retriever), ("Property", prop_retriever)]:
#         results = retriever.retrieve(args.query)
#         print(f"--- Results from {name} Index ---")
#         if not results:
#             print("  No results found.")
#         for i, node_with_score in enumerate(results):
#             print(f"  {i+1}. Score: {node_with_score.score:.4f} | Name: {node_with_score.metadata.get('name', 'N/A')}")
#             print(f"     Text: \"{node_with_score.get_content().replace('\n', ' ')}\"")

if __name__ == "__main__":
    main()
