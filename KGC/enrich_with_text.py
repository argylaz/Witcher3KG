from rdflib import Graph, Namespace, RDF, RDFS, OWL, URIRef, Literal
import re
import os

# --- Configuration ---
KG_INPUT_PATH = '../RDF/Witcher3KG.n3'
CLASSES_INPUT_PATH = '../RDF/Classes.ttl'
ENTITIES_XML_PATH = '../../Wiki_Dump_Namespaces/namespace_0_main.xml'
CATEGORIES_XML_PATH = '../../Wiki_Dump_Namespaces/namespace_14_Category.xml'
KG_OUTPUT_PATH = '../RDF/Witcher3KG_full.ttl'
CLASSES_OUTPUT_PATH = '../RDF/Classes_full.ttl'

# Namespaces
witcher = Namespace("http://cgi.di.uoa.gr/witcher/ontology#")
dbr = Namespace("http://cgi.di.uoa.gr/witcher/resource/")

# --- Helper Function ---
def sanitize_for_uri(text):
    return re.sub(r'\W+', '_', text).strip('_')

# --- Main Enrichment Logic ---
def enrich_graphs_with_text():
    
    # --- Step 1: Load the existing Knowledge Graph and Ontology ---
    kg = Graph()
    classes = Graph()
    print(f"Loading main KG from {KG_INPUT_PATH}...")
    kg.parse(KG_INPUT_PATH, format='n3')
    print(f"Loading ontology from {CLASSES_INPUT_PATH}...")
    # Also load augmentations if you have them, into the same graph
    if os.path.exists('../RDF/Ontology_Augmentations.ttl'):
        classes.parse('../RDF/Ontology_Augmentations.ttl', format='turtle')
    if os.path.exists(CLASSES_INPUT_PATH):
        classes.parse(CLASSES_INPUT_PATH, format='turtle')

    # --- Step 2: Add Full Text to Entities (Instances) ---
    print("\n--- Enriching Entities with Full Text Descriptions ---")
    
    title_pattern = re.compile(r"<title>(.*?)</title>")

    def process_xml_for_full_text(graph, xml_path, uri_builder_func):
        """A generic function to parse a wiki XML dump and add full text."""
        try:
            with open(xml_path, 'r', encoding='utf-8') as file:
                current_title = None
                page_text = ""
                for line in file:
                    title_match = title_pattern.search(line)
                    if title_match:
                        # Process the content for the previous page
                        if current_title and page_text:
                            subject_uri = uri_builder_func(current_title)
                            if (subject_uri, None, None) in graph:
                                graph.add((subject_uri, witcher.hasFullText, Literal(page_text)))
                                print(f"  - Added full text for: {current_title}")
                        
                        # Reset for the new page
                        current_title = title_match.group(1).strip()
                        page_text = ""
                        continue
                    
                    # Accumulate text for the current page
                    if current_title:
                        page_text += line

                # Process the very last page in the file
                if current_title and page_text:
                    subject_uri = uri_builder_func(current_title)
                    if (subject_uri, None, None) in graph:
                        graph.add((subject_uri, witcher.hasFullText, Literal(page_text)))
                        print(f"  - Added full text for: {current_title}")

        except FileNotFoundError:
            print(f"ERROR: Could not find XML file at {xml_path}. Skipping this step.")

    # Run the processor for Entities
    process_xml_for_full_text(kg, ENTITIES_XML_PATH, lambda title: dbr[sanitize_for_uri(title)])

    # --- Step 3: Add Full Text to Classes (from Category pages) ---
    print("\n--- Enriching Classes with Full Text Descriptions ---")
    # Run the processor for Categories
    process_xml_for_full_text(classes, CATEGORIES_XML_PATH, lambda title: witcher[sanitize_for_uri(title.replace("Category:", ""))])
            
    # --- Step 4: Generate and Add Descriptions to Properties ---
    print("\n--- Generating and Enriching Properties with Descriptions ---")
    props_query = "SELECT ?p WHERE { ?p a ?type . FILTER(?type IN (owl:ObjectProperty, owl:DatatypeProperty)) }"
    for row in classes.query(props_query, initNs={"owl": OWL}):
        prop_uri = row.p
        
        # Avoid overwriting if a comment already exists
        if (prop_uri, RDFS.comment, None) in classes:
            continue

        example_query = "SELECT ?s_label ?o_label ?o_val WHERE { ?s ?p ?o . ?s rdfs:label ?s_label . OPTIONAL {?o rdfs:label ?o_label .} BIND(?o as ?o_val) } LIMIT 1"
        example_result = list(kg.query(example_query, initBindings={'p': prop_uri}))
        description = ""
        if example_result:
            ex = example_result[0]
            s_label, o_label, o_val = ex.s_label, ex.o_label, ex.o_val
            o_display = o_label if o_label else o_val
            
            if isinstance(o_val, URIRef):
                description = f"Links a subject to a related entity. Example: '{s_label}' is linked to '{o_display}'."
            else:
                description = f"Assigns a data value to a subject. Example: '{s_label}' has a value of '{o_display}'."
        else:
            description = "A property used in the Witcher knowledge graph."
        classes.add((prop_uri, RDFS.comment, Literal(description)))
        print(f"  - Generated description for property: {prop_uri.split('#')[-1]}")

    # --- Step 5: Save the new, enriched files ---
    print(f"\nSaving enriched knowledge graph to {KG_OUTPUT_PATH}...")
    kg.serialize(destination=KG_OUTPUT_PATH, format='turtle')
    
    print(f"Saving enriched ontology to {CLASSES_OUTPUT_PATH}...")
    classes.serialize(destination=CLASSES_OUTPUT_PATH, format='turtle')
    
    print("\nEnrichment process complete.")

if __name__ == '__main__':
    enrich_graphs_with_text()
