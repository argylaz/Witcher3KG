# evaluate_pipelines_final.py

import json
import argparse
import re
from tqdm import tqdm
from collections import defaultdict
from SPARQLWrapper import SPARQLWrapper, JSON
import time

# Import your pipeline classes from pipelines.py
from pipelines import SimpleRAGPipeline, AgenticRAGPipeline, ExecutionGuidedAgent
10
# --- 1. SETUP ---
SPARQL_ENDPOINT_URL = "http://localhost:7200/repositories/da4dte_final"
NAMESPACES = """
    PREFIX witcher: <http://cgi.di.uoa.gr/witcher/ontology#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX geo: <http://www.opengis.net/ont/geosparql#>
    PREFIX geof: <http://www.opengis.net/def/function/geosparql/>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX dbr: <http://cgi.di.uoa.gr/witcher/resource/>
"""

# --- 2. EVALUATION HELPER FUNCTIONS ---
def clean_sparql_string(sparql_query: str) -> str:
    if not sparql_query: return ""
    return sparql_query.replace('\\n', ' ').replace('\\"', '"').strip()

def extract_answer_keys(sparql_query: str) -> list:
    """
    Intelligently finds the primary "answer" variable from a SELECT clause.
    It prioritizes variables that look like labels or names.
    """
    select_clause_match = re.search(r'SELECT\s+(.*?)\s+WHERE', sparql_query, re.IGNORECASE | re.DOTALL)
    if not select_clause_match:
        return []
    
    select_vars_str = select_clause_match.group(1)
    
    # Find all variables in the select clause
    all_variables = re.findall(r'(\?\w+)', select_vars_str)
    if not all_variables:
        return []

    # Prioritize any variable that contains 'label' or 'name'
    for var in all_variables:
        if 'label' in var.lower() or 'name' in var.lower():
            # Found the semantic answer, return only this key
            return [var.replace('?', '')]
            
    # For comparative queries, the answer is often named '?result'
    if 'AS ?result' in select_vars_str.upper():
        return ['result']

    # Fallback: if no label/name variable is found, return only the first variable
    return [all_variables[0].replace('?', '')]

def execute_and_get_results(sparql_query: str, is_superlative: bool):
    cleaned_query = clean_sparql_string(sparql_query)
    if not cleaned_query or "ERROR" in cleaned_query: return {"error": "Invalid query."}
    full_query = NAMESPACES + cleaned_query
    sparql = SPARQLWrapper(SPARQL_ENDPOINT_URL)
    sparql.setQuery(full_query)
    sparql.setReturnFormat(JSON)
    try:
        results = sparql.query().convert()
        if "boolean" in results: return {"boolean": results["boolean"]}
        bindings = results["results"]["bindings"]
        if is_superlative and bindings: bindings = [bindings[0]]
        canonical_rows = {json.dumps(row, sort_keys=True) for row in bindings}
        return {"rows": canonical_rows, "bindings": bindings}
    except Exception as e:
        return {"error": str(e)}

# --- F1 calculation function ---
def calculate_f1_score(gen_bindings: list, gt_bindings: list, gen_keys: list, gt_keys: list):
    """
    Calculates F1 by comparing the sets of all values in the answer key columns.
    This is robust to different variable names.
    """
    if not isinstance(gen_bindings, list) or not isinstance(gt_bindings, list):
        return 0.0
    
    # Extract all values from all answer key columns for each result set
    gt_answers = {val['value'] for row in gt_bindings for key in gt_keys if key in row for val in [row[key]]}
    gen_answers = {val['value'] for row in gen_bindings for key in gen_keys if key in row for val in [row[key]]}
    
    if not gen_answers and not gt_answers: return 1.0

    true_positives = len(gen_answers.intersection(gt_answers))
    false_positives = len(gen_answers.difference(gt_answers))
    false_negatives = len(gt_answers.difference(gen_answers))
    
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    return f1


def main():
    parser = argparse.ArgumentParser(description="Evaluate RAG-to-SPARQL pipelines using EA and Macro F1-Score.")
    parser.add_argument("--api-key", required=True, help="Your DeepSeek API key.")
    parser.add_argument("--test-file", default="../WitcherBenchmark/validation_set.json", help="The test set to evaluate.")
    parser.add_argument("--output-file", default="pipeline_evaluation_results.json", help="Output file for detailed results.")
    parser.add_argument("--pipelines", nargs='+', choices=['A', 'B', 'C'], default=['A', 'B', 'C'], help="Which pipelines to test.")
    args = parser.parse_args()
  
    # --- Load Test Set & Initialize Pipelines ---
    with open(args.test_file, 'r') as f:
        test_set = json.load(f)
    print(f"Loaded {len(test_set)} queries to evaluate.")
    
    pipelines = {
        'A': SimpleRAGPipeline(api_key=args.api_key) if 'A' in args.pipelines else None,
        'B': AgenticRAGPipeline(api_key=args.api_key) if 'B' in args.pipelines else None,
        'C': ExecutionGuidedAgent(api_key=args.api_key) if 'C' in args.pipelines else None,
    }
    
    # --- Evaluation Loop ---
    detailed_results = []
    ea_scores = defaultdict(int)
    f1_scores = defaultdict(list)
    
    for item in tqdm(test_set, desc="Evaluating Pipelines"):
        question = item['natural_language_question']
        ground_truth_sparql = item['sparql_query']
        template_id = item['template_id']
        is_superlative = template_id in ['T2_ProximitySearch', 'T11_SuperlativeByAttribute']
        
        # Get Ground Truth results for both metrics
        gt_answer_keys = extract_answer_keys(ground_truth_sparql)
        ground_truth_results = execute_and_get_results(ground_truth_sparql, is_superlative)
        
        
        result_entry = {"query_id": item['query_id'], "question": question, "ground_truth_sparql": ground_truth_sparql}

        for p_name, pipeline in pipelines.items():
            if not pipeline: continue
            
            try:
                time.sleep(1) 
                generated_sparql = pipeline.generate_query(question)
                
                # --- Evaluate both metrics ---
                gen_answer_keys = extract_answer_keys(generated_sparql)
                generated_results = execute_and_get_results(generated_sparql, is_superlative)
                
                # EA: Strict comparison of canonical row sets
                is_correct_ea = (
                    "error" not in generated_results and
                    "error" not in ground_truth_results and
                    generated_results.get("rows") == ground_truth_results.get("rows")
                )
                if is_correct_ea:
                    ea_scores[f"pipeline_{p_name}"] += 1

                # F1: Semantic comparison of answer values
                f1 = 0.0
                if "boolean" in ground_truth_results: # ASK queries
                    f1 = 1.0 if generated_results.get("boolean") == ground_truth_results.get("boolean") else 0.0
                else:
                    f1 = calculate_f1_score(
                        generated_results.get("bindings", []),
                        ground_truth_results.get("bindings", []),
                        gen_answer_keys,
                        gt_answer_keys
                    )
                f1_scores[f"pipeline_{p_name}"].append(f1)
                
                result_entry[f"pipeline_{p_name}_generated_sparql"] = generated_sparql
                result_entry[f"pipeline_{p_name}_execution_accuracy_correct"] = is_correct_ea
                result_entry[f"pipeline_{p_name}_f1_score"] = f1

            except Exception as e:
                print(f"\nFATAL ERROR in Pipeline {p_name} for query {item['query_id']}: {e}")
                result_entry[f"pipeline_{p_name}_generated_sparql"] = f"CRASH_ERROR: {e}"
                result_entry[f"pipeline_{p_name}_execution_accuracy_correct"] = False
                result_entry[f"pipeline_{p_name}_f1_score"] = 0.0
                f1_scores[f"pipeline_{p_name}"].append(0.0)

        detailed_results.append(result_entry)

    # --- Calculate and Report Final Scores ---
    total_queries = len(test_set)
    print("\n--- Final Evaluation Results ---")
    print(f"Total Queries Evaluated: {total_queries}")
    
    for p_name in args.pipelines:
        print(f"\n--- Pipeline {p_name} ---")
        # EA Score
        p_ea_score = ea_scores[f"pipeline_{p_name}"]
        p_ea = (p_ea_score / total_queries) * 100
        print(f"  Execution Accuracy (EA): {p_ea_score}/{total_queries} ({p_ea:.2f}%)")
        # F1 Score
        p_f1_scores = f1_scores[f"pipeline_{p_name}"]
        macro_f1 = (sum(p_f1_scores) / len(p_f1_scores)) * 100 if p_f1_scores else 0
        print(f"  Macro F1-Score: {macro_f1:.2f}%")

    # --- Save Detailed Report ---
    print(f"\nSaving detailed results to '{args.output_file}'...")
    with open(args.output_file, 'w') as f:
        json.dump(detailed_results, f, indent=2)
    print("Done!")

if __name__ == "__main__":
    main()