# recalculate_metrics_per_template.py

import json
import argparse
import re
from tqdm import tqdm
from collections import defaultdict
from SPARQLWrapper import SPARQLWrapper, JSON
import time

# --- 1. SETUP & HELPER FUNCTIONS ---
# These are the final, definitive helper functions from our previous discussions.

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

def clean_sparql_string(sparql_query: str) -> str:
    if not sparql_query: return ""
    return sparql_query.replace('\\n', ' ').replace('\\"', '"').strip()

def extract_answer_keys(sparql_query: str) -> list:
    if not sparql_query: return []
    select_clause_match = re.search(r'SELECT\s+(.*?)\s+WHERE', sparql_query, re.IGNORECASE | re.DOTALL)
    if not select_clause_match: return []
    select_vars_str = select_clause_match.group(1)
    all_variables = re.findall(r'(\?\w+)', select_vars_str)
    if not all_variables: return []
    for var in all_variables:
        if 'label' in var.lower() or 'name' in var.lower():
            return [var.replace('?', '')]
    if 'AS ?result' in select_vars_str.upper(): return ['result']
    return [all_variables[0].replace('?', '')]

def execute_and_get_results(sparql_query: str, is_superlative: bool):
    cleaned_query = clean_sparql_string(sparql_query)
    if not cleaned_query or "ERROR" in cleaned_query or "CRASH" in cleaned_query: 
        return {"error": "Invalid query."}
    full_query = NAMESPACES + cleaned_query
    sparql = SPARQLWrapper(SPARQL_ENDPOINT_URL)
    sparql.setQuery(full_query)
    sparql.setReturnFormat(JSON)
    try:
        results = sparql.query().convert()
        if "boolean" in results: return {"boolean": results["boolean"]}
        bindings = results["results"]["bindings"]
        if is_superlative and bindings: bindings = [bindings[0]]
        return {"bindings": bindings}
    except Exception as e:
        return {"error": str(e)}

def calculate_f1_score(gen_bindings: list, gt_bindings: list, gen_query: str, gt_query: str):
    if not isinstance(gen_bindings, list) or not isinstance(gt_bindings, list):
        return 0.0

    gt_label_key = find_label_variable(gt_query)
    gen_label_key = find_label_variable(gen_query)

    if not gt_label_key or not gen_label_key:
        gt_answers = {v['value'] for row in gt_bindings for k, v in row.items()}
        gen_answers = {v['value'] for row in gen_bindings for k, v in row.items()}
    else:
        gt_answers = {row[gt_label_key]['value'] for row in gt_bindings if gt_label_key in row}
        gen_answers = {row[gen_label_key]['value'] for row in gen_bindings if gen_label_key in row}
    
    if not gen_answers and not gt_answers: return 1.0

    true_positives = len(gen_answers.intersection(gt_answers))
    false_positives = len(gen_answers.difference(gt_answers))
    false_negatives = len(gt_answers.difference(gen_answers))
    
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    return f1

def find_label_variable(sparql_query: str) -> str:
    if not sparql_query: return None
    keys = extract_answer_keys(sparql_query)
    return keys[0] if keys else None


def main():
    parser = argparse.ArgumentParser(description="Recalculate metrics per template from a pipeline evaluation results file.")
    parser.add_argument(
        "--input-file", 
        default="pipelineC_evaluation_results_max20.json",
        help="The detailed results file from the evaluate_pipelines.py script."
    )
    args = parser.parse_args()

    # --- Load the existing results ---
    print(f"Loading results from '{args.input_file}'...")
    try:
        with open(args.input_file, 'r') as f:
            detailed_results = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file not found at '{args.input_file}'")
        return

    # --- NEW: Group results by template_id ---
    results_by_template = defaultdict(list)
    for item in detailed_results:
        # Infer template_id if it's missing, for robustness
        query_id = item.get('query_id', '')
        template_id_parts = query_id.split('_')
        template_id = "_".join(template_id_parts[:2]) if len(template_id_parts) >= 2 else 'N/A'
        item['template_id'] = template_id # Ensure it's in the item
        results_by_template[template_id].append(item)

    pipelines_to_check = ['A', 'B', 'C']
    final_report = {}

    print("Recalculating metrics per template with the new logic...")
    # --- NEW: Loop through each template group ---
    for template_id, items in sorted(results_by_template.items()):
        print(f"\n--- Evaluating Template: {template_id} ({len(items)} queries) ---")
        
        template_report = {"query_count": len(items)}
        
        for p_name in pipelines_to_check:
            p_key = f"pipeline_{p_name}"
            if f"{p_key}_generated_sparql" not in items[0]:
                continue
            
            ea_correct_count = 0
            f1_scores = []
            
            for item in items:
                ground_truth_sparql = item['ground_truth_sparql']
                generated_sparql = item[f"{p_key}_generated_sparql"]
                is_superlative = template_id in ['T2_ProximitySearch', 'T11_SuperlativeByAttribute']
                
                # Execute queries to get fresh results
                ground_truth_results = execute_and_get_results(ground_truth_sparql, is_superlative)
                generated_results = execute_and_get_results(generated_sparql, is_superlative)
                
                # Recalculate Execution Accuracy
                gt_rows = {json.dumps(row, sort_keys=True) for row in ground_truth_results.get("bindings", [])}
                gen_rows = {json.dumps(row, sort_keys=True) for row in generated_results.get("bindings", [])}
                is_correct_ea = (
                    "error" not in generated_results and "error" not in ground_truth_results and
                    gen_rows == gt_rows
                )
                if is_correct_ea:
                    ea_correct_count += 1
                
                # Recalculate F1 Score
                f1 = 0.0
                if "boolean" in ground_truth_results:
                    f1 = 1.0 if generated_results.get("boolean") == ground_truth_results.get("boolean") else 0.0
                else:
                    f1 = calculate_f1_score(
                        generated_results.get("bindings", []),
                        ground_truth_results.get("bindings", []),
                        generated_sparql,
                        ground_truth_sparql
                    )
                f1_scores.append(f1)

            # Calculate final metrics for this template and pipeline
            ea_percent = (ea_correct_count / len(items)) * 100
            macro_f1 = (sum(f1_scores) / len(f1_scores)) * 100 if f1_scores else 0
            
            print(f"  - Pipeline {p_name}: EA = {ea_percent:.2f}% | Macro F1 = {macro_f1:.2f}%")
            template_report[p_key] = {"execution_accuracy": ea_percent, "macro_f1_score": macro_f1}
        
        final_report[template_id] = template_report

    # --- Save the detailed per-template report ---
    report_output_file = "pipeline_metrics_per_template.json"
    print(f"\nSaving detailed per-template metrics to '{report_output_file}'...")
    with open(report_output_file, 'w') as f:
        json.dump(final_report, f, indent=2)

if __name__ == "__main__":
    main()