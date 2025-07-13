import re
import json
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, OWL
from rdflib.namespace import XSD
from typing import Union 

# ——————————————————————————————
# 1. Configuration & Initialization
# ——————————————————————————————

# Initialize RDF Graph and Namespaces
g = Graph()
witcher = Namespace("http://cgi.di.uoa.gr/witcher/ontology#")
dbr = Namespace("http://cgi.di.uoa.gr/witcher/resource/")
GEO = Namespace("http://www.opengis.net/ont/geosparql#")
g.bind("geo", GEO)


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


# Gemeric function to integrate GeoSPARQL data from an Esri JSON file
def integrate_geo_file(graph, json_path, feature_class, map_context_uri, uri_prefix=None, name_attribute=None):
    """
    Reads an Esri JSON file and adds GeoSPARQL data to the graph for each feature.
    Handles both Polygons (rings) and Polylines (paths).

    :param graph: The rdflib.Graph to add triples to.
    :param json_path: Path to the Esri JSON file.
    :param feature_class: The RDF class to assign to each feature (e.g., witcher.Swamp).
    :param map_context_uri: The URI of the map context (e.g., ).
    :param uri_prefix: (Optional) A string to prepend to URIs for anonymous features (e.g., "Novigrad").
    :param name_attribute: (Optional) The key for the name in the attributes dictionary.
                           If provided, uses the name for the URI.
                           If None, creates a new URI based on the OBJECTID.
    """
    # Robustly get the local name of the class (e.g., "Swamp")
    local_class_name = str(feature_class).split('/')[-1].split('#')[-1]
    print(f"\n--- Integrating GeoSPARQL data for {local_class_name} from {json_path} ---")

    try:
        with open(json_path, 'r', encoding='utf-16') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Geospatial file not found at {json_path}")
        return
    except Exception as e:
        print(f"An error occurred reading or parsing {json_path}: {e}")
        return

    for feature in data.get('features', []):
        attributes = feature.get('attributes', {})
        geometry = feature.get('geometry', {})

        subject_uri = None
        if name_attribute:
            # Logic for named features (like cities e.g. dbr:Oxenfurt)
            name = attributes.get(name_attribute)
            if name:
                subject_uri = dbr[sanitize_for_uri(name)]
        else:
            # Logic for anonymous features (like swamps e.g. dbr:Novigrad_Swamp_1)
            object_id = attributes.get('OBJECTID')
            if object_id:
                uri_base = f"{uri_prefix}_{local_class_name}_{object_id}" if uri_prefix else f"{local_class_name}_{object_id}"
                subject_uri = dbr[sanitize_for_uri(uri_base)]
        
        if not subject_uri:
            print(f"Warning: Could not determine a URI for a feature in {json_path}. Skipping.")
            continue

        geometry_uri = URIRef(f"{subject_uri}_geometry")
        wkt_string = None

        if 'rings' in geometry: # It's a Polygon
            points = geometry['rings'][0]
            wkt_points = ", ".join([f"{p[0]} {p[1]}" for p in points])
            wkt_string = f"POLYGON (({wkt_points}))"
        elif 'paths' in geometry: # It's a Polyline (Roads)
            path_strings = []
            for path in geometry['paths']:
                path_points = ", ".join([f"{p[0]} {p[1]}" for p in path])
                path_strings.append(f"({path_points})")
            wkt_string = f"MULTILINESTRING ({', '.join(path_strings)})"
        
        if not wkt_string:
            print(f"Warning: No valid geometry found for {subject_uri}. Skipping.")
            continue
            
        wkt_literal = Literal(wkt_string, datatype=GEO.wktLiteral)
        
        # Add triples
        graph.add((subject_uri, RDF.type, GEO.Feature))       # GeoSPARQL type
        graph.add((subject_uri, RDF.type, feature_class))     # Specific domain type
        graph.add((subject_uri, GEO.hasGeometry, geometry_uri))
        graph.add((subject_uri, witcher.isPartOf, map_context_uri)) # Link to map
        graph.add((geometry_uri, RDF.type, GEO.Geometry))
        graph.add((geometry_uri, GEO.asWKT, wkt_literal))
        
        if 'Shape__Area' in attributes:
            graph.add((geometry_uri, witcher.shapeArea, Literal(attributes['Shape__Area'], datatype=XSD.double)))
        if 'Shape__Length' in attributes:
            graph.add((geometry_uri, witcher.shapeLength, Literal(attributes['Shape__Length'], datatype=XSD.double)))

        print(f"  - Added GeoSPARQL data for: {subject_uri}")


# Function to add a map border geometry directly to the map entity
def add_map_border_geometry(graph, json_path, map_uri):
    """
    Reads a border file and assigns its geometry directly to the map entity.
    """
    print(f"\n--- Defining Geometry for Map <{map_uri}> from {json_path} ---")
    try:
        with open(json_path, 'r', encoding='utf-16') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading or parsing border file {json_path}: {e}")
        return

    # Assuming the border file contains a single feature representing the whole map
    feature = data.get('features', [{}])[0]
    geometry = feature.get('geometry', {})

    if 'rings' in geometry:
        geometry_uri = URIRef(f"{map_uri}_geometry")
        points = geometry['rings'][0]
        wkt_points = ", ".join([f"{p[0]} {p[1]}" for p in points])
        wkt_string = f"POLYGON (({wkt_points}))"
        wkt_literal = Literal(wkt_string, datatype=GEO.wktLiteral)

        graph.add((map_uri, RDF.type, witcher.Map))
        graph.add((map_uri, RDF.type, GEO.Feature))
        graph.add((map_uri, RDFS.label, Literal("Novigrad and Velen Map")))
        graph.add((map_uri, GEO.hasGeometry, geometry_uri))
        graph.add((geometry_uri, RDF.type, GEO.Geometry))
        graph.add((geometry_uri, GEO.asWKT, wkt_literal))
        print(f"  - Successfully attached border geometry to {map_uri.n3(graph.namespace_manager)}")


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


# --- CALL THE GEOSPATIAL INTEGRATION FUNCTIONs FOR EACH FILE (We only havre Geospatial info for novigrad map) ---


# 1. Define the central URI for the map itself
novigrad_map_uri = dbr.Novigrad_And_Velen_Map
g.add((novigrad_map_uri, RDF.type, witcher.Map))
g.add((novigrad_map_uri, RDFS.label, Literal("Novigrad and Velen Map")))
g.add((dbr.Novigrad, witcher.isPartOf, novigrad_map_uri))  # Link Novigrad to the map (with isPartOf)
g.add((dbr.Velen, witcher.isPartOf, novigrad_map_uri))  # Link Velen to the map (with isPartOf)

# 2. Add the border geometry TO the map URI
borders_file = '../InfoFiles/novigrad_borders.json'
add_map_border_geometry(g, borders_file, novigrad_map_uri)

# 3. Integrate all other features and link them TO the map URI
cities_file = '../InfoFiles/novigrad_cities.json'
integrate_geo_file(g, cities_file, witcher.City, novigrad_map_uri, name_attribute='name')

swamps_file = '../InfoFiles/novigrad_swamps.json'
integrate_geo_file(g, swamps_file, witcher.Swamp, novigrad_map_uri, uri_prefix="Novigrad")

lakes_file = '../InfoFiles/novigrad_lakes.json'
integrate_geo_file(g, lakes_file, witcher.Lake, novigrad_map_uri, uri_prefix="Novigrad")

terrain_file = '../InfoFiles/novigrad_terrain.json'
integrate_geo_file(g, terrain_file, witcher.Terrain, novigrad_map_uri, uri_prefix="Novigrad")

roads_file = '../InfoFiles/novigrad_roads.json'
integrate_geo_file(g, roads_file, witcher.Road, novigrad_map_uri, uri_prefix="Novigrad")


# ——————————————————————————————
# 5. Save Final RDF Output
# ——————————————————————————————

output_file = '../RDF/main_linked.n3'
g.serialize(output_file, format='n3')

print("\n-------------------------------------------")
print(f"Processing complete.")
print(f"Generated {len(g)} triples.")
print(f"Final linked RDF graph saved to: {output_file}")