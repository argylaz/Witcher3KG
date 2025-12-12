from rdflib import Graph, Namespace, RDF, RDFS, OWL, URIRef, Literal
import re

# --- Configuration ---
KG_INPUT_PATH = '../RDF/Witcher3KG.n3'
CLASSES_INPUT_PATH = '../RDF/Classes.ttl'
ENTITIES_XML_PATH = '../Wiki_Dump_Namespaces/namespace_0_main.xml'
KG_OUTPUT_PATH = '../RDF/Witcher3KG_full.ttl'
CLASSES_OUTPUT_PATH = '../RDF/Classes_full.ttl'

# Namespaces
witcher = Namespace("http://cgi.di.uoa.gr/witcher/ontology#")
dbr = Namespace("http://cgi.di.uoa.gr/witcher/resource/")

# --- Helper Functions ---
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
    classes.parse(CLASSES_INPUT_PATH, format='turtle')

    # --- Step 2: Add FULL TEXT ONLY (no first paragraph, no comments) ---
    print("\n--- Enriching Entities with Full Text Descriptions ---")
    
    title_pattern = re.compile(r"<title>(.*?)</title>")

    def process_entity_page_for_text(title, text, graph):
        """Add only full wikitext to the entity."""
        if not title or not text:
            return
        
        subject_uri = dbr[sanitize_for_uri(title)]

        # Only enrich if entity exists in the graph
        if (subject_uri, None, None) in graph:

            # Add full raw wikitext
            graph.add((subject_uri, witcher.hasFullText, Literal(text)))
            print(f"  - Added full text for entity: {title}")

    try:
        with open(ENTITIES_XML_PATH, 'r', encoding='utf-8') as file:
            current_title = None
            page_text = ""

            for line in file:
                title_match = title_pattern.search(line)

                if title_match:
                    # Commit previous page
                    process_entity_page_for_text(current_title, page_text, kg)

                    # Reset for new page
                    current_title = title_match.group(1).strip()
                    page_text = ""
                    continue

                # Accumulate text
                if current_title:
                    page_text += line

            # Process last page
            process_entity_page_for_text(current_title, page_text, kg)

    except FileNotFoundError:
        print(f"ERROR: Could not parse {ENTITIES_XML_PATH}. Skipping entity enrichment.")

    # --- Step 3: Generate and Add Descriptions to Classes (unchanged) ---
    print("\n--- Generating and Enriching Classes with Descriptions ---")
    class_query = "SELECT ?cls ?label WHERE { ?cls a owl:Class . ?cls rdfs:label ?label . }"
    
    for row in classes.query(class_query, initNs={"owl": OWL}):
        class_uri, class_label = row.cls, row.label
        
        instance_query = """
            SELECT ?inst_label ?inst_comment
            WHERE {
                ?inst a ?c .
                ?inst rdfs:label ?inst_label .
                ?inst rdfs:comment ?inst_comment .
            } LIMIT 3
        """

        example_instances = list(kg.query(instance_query, initBindings={'c': class_uri}))
        
        if example_instances:
            desc_parts = [f"This class represents entities of type '{class_label}'. Example instances include:"]
            for inst_row in example_instances:
                desc_parts.append(f"- {inst_row.inst_label}: {inst_row.inst_comment}")
            
            generated_desc = " ".join(desc_parts)
            classes.add((class_uri, RDFS.comment, Literal(generated_desc)))
            print(f"  - Generated description for class: {class_label}")

    # --- Step 4: Generate and Add Descriptions to Properties (unchanged) ---
    print("\n--- Generating and Enriching Properties with Descriptions ---")
    props_query = "SELECT ?p WHERE { ?p a ?type . FILTER(?type IN (owl:ObjectProperty, owl:DatatypeProperty)) }"

    for row in classes.query(props_query, initNs={"owl": OWL}):
        prop_uri = row.p

        example_query = """
            SELECT ?s_label ?o_label ?o_val
            WHERE {
                ?s ?p ?o .
                ?s rdfs:label ?s_label .
                OPTIONAL {?o rdfs:label ?o_label .}
                BIND(?o AS ?o_val)
            }
            LIMIT 1
        """

        example_result = list(kg.query(example_query, initBindings={'p': prop_uri}))

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

    # --- Step 5: Save enriched graphs ---
    print(f"\nSaving enriched knowledge graph to {KG_OUTPUT_PATH}...")
    kg.serialize(destination=KG_OUTPUT_PATH, format='turtle')
    
    print(f"Saving enriched ontology to {CLASSES_OUTPUT_PATH}...")
    classes.serialize(destination=CLASSES_OUTPUT_PATH, format='turtle')
    
    print("\nEnrichment process complete.")

if __name__ == '__main__':
    enrich_graphs_with_text()
