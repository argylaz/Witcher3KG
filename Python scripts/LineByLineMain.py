import re
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, OWL
from typing import Union 

# ——————————————————————————————
# 1. Configuration & Initialization
# ——————————————————————————————

# Initialize RDF Graph and Namespaces
g = Graph()
witcher = Namespace("http://cgi.di.uoa.gr/witcher/ontology#")
dbr = Namespace("http://cgi.di.uoa.gr/witcher/resource/")

# Bind namespaces for cleaner RDF output
g.bind("witcher", witcher)
g.bind("dbr", dbr)
g.bind("rdfs", RDFS)
g.bind("owl", OWL)

# ——————————————————————————————
# 2. Pre-load Ontology & Define Regex
# ——————————————————————————————

# Load ontology to get existing OWL classes for typing instances
try:
    g.parse('../RDF/Classes.ttl', format='turtle')
    existing_classes = set()
    for s in g.subjects(RDF.type, OWL.Class):
        if isinstance(s, URIRef) and s.startswith(str(witcher)):
            class_name = s.split('#')[-1].replace('_', ' ')
            existing_classes.add(class_name.lower())
    print(f"Successfully loaded {len(existing_classes)} OWL Classes.")
except FileNotFoundError:
    print("Warning: Classes.ttl not found. No instances will be typed from categories.")
    existing_classes = set()


### Regex patterns for XML/Wikitext extraction  ###
 
title_pattern = re.compile(r"<title>(.*?)</title>")               # Used for page titles

category_pattern = re.compile(r"\[\[Category:(.*?)\]\]")          # Used for extracting categories (class types)
infobox_pattern = re.compile(r"\{\{Infobox (.*?)\}\}", re.DOTALL) # Used for extracting infobox data (property/value pairs)

infobox_property_pattern = re.compile(
    r"^\|\s*([^=]+?)\s*=\s*(.*?)(?=\n\s*\||\n\s*\}\})",           # stops at the next property or end of infobox using lookahead
    re.DOTALL | re.MULTILINE                                      # DOTALL allows . to match newlines
)

br_split_pattern = re.compile(r'<br\s*/?\s*>', re.IGNORECASE)     # Used to split infobox values that use <br> tags

# This pattern is for FINDING all links inside a value. It returns a list of strings.
wikilink_find_pattern = re.compile(r'\[\[([^|\]]+)(?:\|[^\]]+)?\]\]')

# ——————————————————————————————
# 3. Processing Logic
# ——————————————————————————————

def sanitize_for_uri(text):
    """Replaces spaces with underscores and removes characters invalid for a URI path segment."""
    return re.sub(r'\W+', '_', text).strip('_')


def find_infobox_content(page_text: str) -> Union[str, None]:
    """
    Finds the full content of an infobox by correctly handling nested braces.
    Returns the content inside the main {{Infobox ... }} block, or None if not found.
    """
    try:
        # Find the starting position of "{{Infobox" (case-insensitive)
        start_marker = "{{Infobox"
        start_index = page_text.lower().find(start_marker.lower())
        if start_index == -1:
            return None

        # Start scanning from after the opening "{{" of the infobox
        search_start = start_index + 2
        brace_level = 2  # We start inside the first "{{"
        
        # We need the content *after* the "Infobox" part.
        # Find the end of the line of "{{Infobox <type>" to get the body
        infobox_body_start = page_text.find('\n', start_index)
        if infobox_body_start == -1:
             # This is a very unusual case, maybe a one-line infobox.
             infobox_body_start = start_index + len(start_marker)

        i = search_start
        while i < len(page_text) - 1:
            if page_text[i:i+2] == '{{':
                brace_level += 2
                i += 2
            elif page_text[i:i+2] == '}}':
                brace_level -= 2
                if brace_level == 0:
                    # Found the matching closing brace
                    # The content is from after the start marker to the closing brace
                    return page_text[infobox_body_start:i]
                i += 2
            else:
                i += 1
        return None # No matching closing brace found
    except Exception:
        # Failsafe in case of any string processing error
        return None


def clean_value(value: str) -> str:
    """
    Cleans a raw wikitext value that does NOT contain links.
    Its main job is to remove leftover templates and markup.
    """
    # Remove any remaining templates like {{...}}
    while re.search(r'\{\{[^\{\}]*?\}\}', value):
         value = re.sub(r'\{\{[^\{\}]*?\}\}', '', value)

    # Remove any leftover link brackets, quotes, etc.
    value = value.replace("'''", "").replace("''", "")
    value = value.replace('[[', '').replace(']]', '')
    return value.strip()


def process_page_content(title, text, graph):
    """
    Extracts categories and infobox data from a wiki page's text and adds triples to the graph.
    """
    if not title or not text:
        return

    subject_uri = dbr[sanitize_for_uri(title)]
    
    # --- Process Categories to assign rdf:type ---
    categories = category_pattern.findall(text)
    is_instance_created = False
    for cat in categories:
        cat_name = cat.split('|')[0].strip().replace('_', ' ')
        if cat_name.lower() in existing_classes:
            # Clean category name for URI
            class_uri = witcher[cat_name.replace(' ', '_')]
            graph.add((subject_uri, RDF.type, class_uri))
            
            # Add the label only once
            if not is_instance_created:
                graph.add((subject_uri, RDFS.label, Literal(title)))
                print(f"Created instance: {title} -> rdf:type witcher:{cat_name.replace(' ', '_')}")
                is_instance_created = True
 
    # --- Process Infobox ---
    infobox_body = find_infobox_content(text)
    if infobox_body:
        if not is_instance_created:
            graph.add((subject_uri, RDFS.label, Literal(title)))

        # The infobox_property_pattern can now run on the *complete* and correct body
        for prop_name, raw_value in infobox_property_pattern.findall(infobox_body):
            prop_name_clean = prop_name.strip()
            prop_uri = witcher[sanitize_for_uri(prop_name_clean)]
            
            values = [v.strip() for v in br_split_pattern.split(raw_value) if v.strip()] # Split value by <br> tags and clean whitespace

            for value in values:
                # 1. Try to find all linkable entities within the value
                found_links = wikilink_find_pattern.findall(value)
                
                # 2. For each link found, create a separate object property (a structured link)
                # This correctly loops over a list of strings.
                for link_target in found_links:
                    link_target = link_target.strip()
                    if link_target:
                        linked_uri = dbr[sanitize_for_uri(link_target)]
                        graph.add((subject_uri, prop_uri, linked_uri)) 
                        print(f"  - Added object property: {title} -> {prop_name_clean} -> {link_target}")

                # 3. ALWAYS clean the original value and add it as a single data property.
                # This preserves the full human-readable text context.
                cleaned_literal = clean_value(value)
                if cleaned_literal:
                    graph.add((subject_uri, prop_uri, Literal(cleaned_literal)))
                    print(f"  - Added data property: {title} -> {prop_name_clean} = '{cleaned_literal}'")


# ——————————————————————————————
# 4. Main Execution: Read XML and Build Graph
# ——————————————————————————————

input_file = '../Wiki_Dump_Namespaces/namespace_0_main.xml'
print(f"\nStarting processing of {input_file}...")

with open(input_file, 'r', encoding='utf-8') as file:
    current_title = None
    page_text = ""
    
    for line in file:
        title_match = title_pattern.search(line)
        if title_match:
            # When a new <title> is found, it means the previous page has ended.
            # Process the content we've accumulated for the previous page.
            process_page_content(current_title, page_text, g)
            
            # Reset for the new page
            current_title = title_match.group(1).strip()
            page_text = ""
            continue # Skip to the next line

        # Accumulate text for the current page
        if current_title:
            page_text += line

    # Process the very last page in the file after the loop finishes
    process_page_content(current_title, page_text, g)

# ——————————————————————————————
# 5. Save Final RDF Output
# ——————————————————————————————

output_file = '../RDF/main_linked.n3'
g.serialize(output_file, format='n3')

print("\n-------------------------------------------")
print(f"Processing complete.")
print(f"Generated {len(g)} triples.")
print(f"Final linked RDF graph saved to: {output_file}")