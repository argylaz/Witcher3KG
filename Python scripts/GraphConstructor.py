import re
import json
import xml.etree.ElementTree as ET
import numpy as np
from shapely.geometry import Point, Polygon, MultiLineString
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, OWL
from rdflib.namespace import XSD
from typing import Tuple, Optional, Union

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


city_names = []    # For contextual matching of map pins
city_polygons = {} # For storing city polygons


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


def parse_esri_rings(rings_array):
    """
    Parses an Esri JSON 'rings' array into a list of shapely Polygons,
    correctly handling MultiPolygon features by treating each ring as a separate polygon.
    """
    if not rings_array: return []
    
    ring_list = rings_array
    # Intelligently flatten the common extra nesting level in Esri JSON
    while len(ring_list) == 1 and isinstance(ring_list[0], list) and isinstance(ring_list[0][0], list):
        ring_list = ring_list[0]
        
    polygons = []
    for ring_points in ring_list:
        try:
            # A valid ring must have at least 4 points to close
            if isinstance(ring_points, list) and len(ring_points) >= 4:
                poly = Polygon(ring_points)
                if not poly.is_valid:
                    poly = poly.buffer(0) # Attempt to fix invalid geometry
                polygons.append(poly)
        except Exception as e:
            print(f"  - Warning: Could not create a polygon from a ring. Error: {e}")
            continue
            
    return polygons


# Gemeric function to integrate GeoSPARQL data from an Esri JSON file
def integrate_geo_file(graph, json_path, feature_class, map_context_uri, uri_prefix=None, name_attribute=None):
    """
    Reads an Esri JSON file and adds GeoSPARQL data to the graph for each feature.
    Handles both Polygons, MultiPolygons, and Polylines.
    """
    local_class_name = str(feature_class).split('/')[-1].split('#')[-1]
    print(f"\n--- Integrating {local_class_name} features from {json_path} ---")

    try:
        with open(json_path, 'r', encoding='utf-16') as f:
            data = json.load(f)
    except Exception as e:
        print(f"An error occurred reading or parsing {json_path}: {e}")
        return

    for feature in data.get('features', []):
        attributes = feature.get('attributes', {})
        geometry = feature.get('geometry', {})

        # --- Subject URI Creation (Logic is unchanged) ---
        subject_uri = None
        name = None
        if name_attribute:
            name = attributes.get(name_attribute)
            if name:
                subject_uri = dbr[sanitize_for_uri(name)]
                # Populate global lists for contextual linking
                if name.lower() not in city_names: city_names.append(name.lower())
                if feature_class == witcher.City and 'rings' in geometry:
                    # Use the robust parser to handle city polygons too
                    city_polys = parse_esri_rings(geometry['rings'])
                    if city_polys: city_polygons[name.lower()] = city_polys[0]
        else:
            object_id = attributes.get('OBJECTID')
            if object_id:
                uri_base = f"{uri_prefix}_{local_class_name}_{object_id}"
                subject_uri = dbr[sanitize_for_uri(uri_base)]
        
        if not subject_uri:
            continue

        # --- GEOMETRY PARSING AND TRIPLE CREATION (THE CRITICAL FIX) ---
        
        # This block replaces the old wkt_string creation
        if 'rings' in geometry:
            # Use the new robust parser which returns a LIST of polygons
            polygons_in_feature = parse_esri_rings(geometry['rings'])
            
            # If it's a true multipolygon, create a unique geometry for each part
            if len(polygons_in_feature) > 1:
                for i, poly in enumerate(polygons_in_feature):
                    # Create a unique geometry URI for each part, e.g., ..._geometry_part_1
                    geometry_uri = URIRef(f"{subject_uri}_geometry_part_{i+1}")
                    wkt_literal = Literal(poly.wkt, datatype=GEO.wktLiteral)
                    
                    # Add triples for this specific polygon part
                    graph.add((subject_uri, GEO.hasGeometry, geometry_uri))
                    graph.add((geometry_uri, RDF.type, GEO.Geometry))
                    graph.add((geometry_uri, GEO.asWKT, wkt_literal))
            
            # If it's a simple polygon, add it directly
            elif len(polygons_in_feature) == 1:
                geometry_uri = URIRef(f"{subject_uri}_geometry")
                wkt_literal = Literal(polygons_in_feature[0].wkt, datatype=GEO.wktLiteral)
                
                graph.add((subject_uri, GEO.hasGeometry, geometry_uri))
                graph.add((geometry_uri, RDF.type, GEO.Geometry))
                graph.add((geometry_uri, GEO.asWT, wkt_literal))

        elif 'paths' in geometry:
            # Road logic is unchanged, it was already correct
            geometry_uri = URIRef(f"{subject_uri}_geometry")
            line = MultiLineString(geometry['paths'])
            wkt_literal = Literal(line.wkt, datatype=GEO.wktLiteral)
            
            graph.add((subject_uri, GEO.hasGeometry, geometry_uri))
            graph.add((geometry_uri, RDF.type, GEO.Geometry))
            graph.add((geometry_uri, GEO.asWKT, wkt_literal))

        # --- Add Common Triples (Type, Context, and Attributes) ---
        # This part runs for all geometry types
        graph.add((subject_uri, RDF.type, GEO.Feature))
        graph.add((subject_uri, RDF.type, feature_class))
        graph.add((subject_uri, witcher.isPartOf, map_context_uri))
        
        # Add shape area/length to the primary geometry URI if they exist
        primary_geom_uri = URIRef(f"{subject_uri}_geometry") # Default URI
        if 'rings' in geometry and len(parse_esri_rings(geometry['rings'])) > 1:
             # For multipolygons, we can't assign area to a single part,
             # so we could either skip it or assign it to the main feature URI.
             # For now, we'll just add it to the main feature.
             primary_geom_uri = subject_uri

        if 'Shape__Area' in attributes:
            graph.add((primary_geom_uri, witcher.shapeArea, Literal(attributes['Shape__Area'], datatype=XSD.double)))
        if 'Shape__Length' in attributes:
            graph.add((primary_geom_uri, witcher.shapeLength, Literal(attributes['Shape__Length'], datatype=XSD.double)))
            
        print(f"  - Successfully processed GeoSPARQL data for: {subject_uri.n3(graph.namespace_manager)}")

# Function to add a map border geometry directly to the map entity
def add_map_border_geometry(graph, json_path, map_uri) -> Optional[Tuple[Point,Point, Point]]:
    """
    Reads a border file and assigns its geometry directly to the map entity.
    Returns the centroid and northernmost point of the border polygon.
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
        # Define shapely polygon and calculate centroid
        all_points = geometry['rings'][0]
        poly = Polygon(all_points)
        centroid = poly.centroid

        # Find the top-right and top-left corner points of the border
        min_x, min_y, max_x, max_y = poly.bounds
        top_right_corner = (max_x, max_y)
        top_left_corner = (min_x, max_y)

        geometry_uri = URIRef(f"{map_uri}_geometry")
        points = geometry['rings'][0]
        wkt_points = ", ".join([f"{p[0]} {p[1]}" for p in points])
        wkt_string = f"POLYGON (({wkt_points}))"
        wkt_literal = Literal(wkt_string, datatype=GEO.wktLiteral)

        graph.add((map_uri, RDF.type, witcher.Maps))
        graph.add((map_uri, RDF.type, GEO.Feature))
        graph.add((map_uri, RDFS.label, Literal("Novigrad and Velen Map")))
        graph.add((map_uri, GEO.hasGeometry, geometry_uri))
        graph.add((geometry_uri, RDF.type, GEO.Geometry))
        graph.add((geometry_uri, GEO.asWKT, wkt_literal))
        print(f"  - Successfully attached border geometry to {map_uri.n3(graph.namespace_manager)}")

        return (centroid, top_right_corner, top_left_corner)
    return None

# Function to calculate an affine transformation matrix
# This is used to convert game coordinates to GIS coordinates
def calculate_affine_transform(game_coords, gis_coords):
    """
    Calculates the 2D affine transformation matrix using a robust
    least-squares method that is stable for 3 or more points.
    """
    game_pts = np.array(game_coords)
    gis_pts = np.array(gis_coords)
    
    # Pad the game coordinates with a column of ones to handle translation
    A = np.hstack([game_pts, np.ones((game_pts.shape[0], 1))])
    
    # Use least squares to solve for the transformation parameters for X and Y
    # This is more robust than np.linalg.solve for this problem
    try:
        params_x, _, _, _ = np.linalg.lstsq(A, gis_pts[:, 0], rcond=None)
        params_y, _, _, _ = np.linalg.lstsq(A, gis_pts[:, 1], rcond=None)
    except np.linalg.LinAlgError as e:
        print(f"!!! FATAL LINALG ERROR: {e} !!!")
        print("This means your control points are still collinear. You must choose points that form a triangle.")
        return None
    
    # The solution gives us the rows of the 2x3 transformation matrix
    transform_matrix = np.array([params_x, params_y])
    
    print("\n--- Calculated Transformation Matrix ---")
    print(transform_matrix)
    return transform_matrix
 
def transform_point(point, matrix):
    game_pt = np.array([point[0], point[1], 1])
    gis_pt = matrix @ game_pt     # Apply transformation
    return (gis_pt[0], gis_pt[1]) 
 
# Map pin integration logic
def integrate_map_pins(graph, xml_path, transform_matrix):
    """
    The definitive function to integrate map pins. It uses a multi-pass strategy to
    correctly link entities, merge duplicate pins with multiple roles (e.g., Armorer + GwentPlayer),
    and intelligently infer types from pin names.
    """
    print(f"\n--- Integrating and Linking Map Pins from {xml_path} ---")

    # 1. Build a lookup map of {lowercase_label: uri} from the existing graph
    label_to_uri_map = {
        str(o).lower(): s
        for s, o in graph.subject_objects(RDFS.label)
        # if isinstance(o, Literal)
    }
    print(f"  - Built lookup map with {len(label_to_uri_map)} existing labels.")

    # A list of generic names that REQUIRE spatial context for accurate linking
    keyword_to_type = {
        'blacksmith': witcher.Blacksmith, 'armorer': witcher.Armorer,
        'merchant': witcher.Merchant, 'innkeep': witcher.Innkeep,
        'herbalist': witcher.Herbalist, 'whetstone': witcher.Whetstone,
        'notice board': witcher.NoticeBoard, 'road sign': witcher.RoadSign
    }
    generic_pin_names = list(keyword_to_type.keys())

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        print(f"Error parsing {xml_path}: {e}"); return

    # Pass 2: The Main Linking Loop
    for world in root.findall('world'):
        world_name = world.get('name')
        world_map_uri = dbr[sanitize_for_uri(f"{world_name}_Map")]
        graph.add((world_map_uri, RDF.type, witcher.Map))
        graph.add((world_map_uri, RDFS.label, Literal(f"{world_name} Map")))

        for mappin in world.findall('mappin'):
            name_elem = mappin.find('name'); pos = mappin.find('position'); mappin_type_str = mappin.get('type')
            if not all([name_elem, name_elem.text, pos, mappin_type_str]): continue

            name = name_elem.text.strip()
            name_lower = name.lower()
            game_x, game_y = float(pos.get('x')), float(pos.get('y'))
            coord_key = f"{game_x},{game_y}"
            
            subject_uri = None
            
            # Step A: Have we already processed a pin at this exact location?
            if coord_key in coords_to_uri_map:
                subject_uri = coords_to_uri_map[coord_key]
                print(f"  - Found duplicate pin at {coord_key}. Merging roles for: {subject_uri.n3(graph.namespace_manager)}")
            
            # Step B: If not, this is the first pin at this location. Find or create its entity.
            else:
                # This is a new location, so we find/create its URI and add its geometry
                gis_x, gis_y = transform_point((game_x, game_y), transform_matrix)
                pin_point = Point(gis_x, gis_y)
                
                # Tier 1: Spatially-aware contextual match
                found_match = False
                for city_name, city_poly in city_polygons.items():
                    if pin_point.within(city_poly):
                        contextual_label = f"{name} ({city_name})"
                        if contextual_label.lower() in label_to_uri_map:
                            subject_uri = label_to_uri_map[contextual_label.lower()]
                            print(f"  - Spatially & contextually matched '{name}' in '{city_name}' to: {subject_uri.n3(graph.namespace_manager)}")
                            found_match = True
                        break

            else:
                # 2. If the name is NOT generic (e.g., a quest), do a direct match
                if name.lower() in label_to_uri_map:
                    subject_uri = label_to_uri_map[name.lower()]
                    print(f"  - Matched unique pin '{name}' to existing entity: {subject_uri.n3(graph.namespace_manager)}")
     
            # Fallback: If no match was found by any method, create a new entity for the pin.

            # 3. No match found, create a new, clean URI for a generic pin
            if not subject_uri:
                # Create a clean, unique URI using coordinates to avoid name collisions
                safe_x = str(game_x).replace('-', 'm').replace('.', 'p')
                safe_y = str(game_y).replace('-', 'm').replace('.', 'p')
                uri_base = f"{world_name}_{name}_Pin_{safe_x}_{safe_y}"
                subject_uri = dbr[sanitize_for_uri(uri_base)]
                
                # Add the essential types and label for this new entity
                graph.add((subject_uri, RDFS.label, Literal(name)))
                print(f"  - No match found. Created new pin entity '{name}': {subject_uri.n3(graph.namespace_manager)}")
 

            # --- Augment BOTH matched and new entities with pin info ---
            # 1. This entity is now a geo:Feature
            graph.add((subject_uri, RDF.type, GEO.Feature))
            graph.add((subject_uri, RDF.type, witcher[sanitize_for_uri(mappin_type)])) 
            
            # 2. Add other pin-specific properties and infer other mappin types
            if internal_name:
                graph.add((subject_uri, witcher.hasInternalName, Literal(internal_name)))
                for keyword, rdf_class in keyword_to_type.items():
                    if keyword in name.lower():
                        graph.add((subject_uri, RDF.type, rdf_class))
                        print(f"    - Inferred and added type '{str(rdf_class).split('#')[-1]}' from name for {subject_uri.n3(graph.namespace_manager)}")
            
            # Add relationship linking this feature to the map it's on
            graph.add((subject_uri, witcher.isPartOf, world_map_uri))

            # 3. Create and add the point geometry, using the GIS coordinates
            wkt_point = f"POINT ({gis_x} {gis_y})"
            wkt_literal = Literal(wkt_point, datatype=GEO.wktLiteral)
            # Using a new geometry URI to avoid conflicts
            geometry_uri = URIRef(f"{subject_uri}_point_geometry")

            graph.add((subject_uri, GEO.hasGeometry, geometry_uri))
            graph.add((geometry_uri, RDF.type, GEO.Geometry))
            graph.add((geometry_uri, GEO.asWKT, wkt_literal))

            # --- Step C: Augment the found/created entity with ALL relevant types ---
            # 1. Add the type from the XML attribute (e.g., GwentPlayer)
            graph.add((subject_uri, RDF.type, witcher[sanitize_for_uri(mappin_type_str)]))

            # 2. Infer and add a primary type from keywords in the name string
            for keyword, rdf_class in keyword_to_type.items():
                if keyword in name_lower:
                    graph.add((subject_uri, RDF.type, rdf_class))
                    print(f"    - Inferred and added type '{str(rdf_class).split('#')[-1]}' from name.")


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
novigrad_map_uri = dbr.Velen_Novigrad_Map
g.add((novigrad_map_uri, RDF.type, witcher.Maps))
g.add((novigrad_map_uri, RDFS.label, Literal("Novigrad and Velen Map")))
g.add((dbr.Novigrad, witcher.isPartOf, novigrad_map_uri))  # Link Novigrad to the map (with isPartOf)
g.add((dbr.Velen, witcher.isPartOf, novigrad_map_uri))  # Link Velen to the map (with isPartOf)

# 2. Add the border geometry TO the map URI
borders_file = '../InfoFiles/novigrad_borders.json'
gis_control_data = add_map_border_geometry(g, borders_file, novigrad_map_uri)

# 3. Integrate all other features and link them TO the map URI
swamps_file = '../InfoFiles/novigrad_swamps.json'
integrate_geo_file(g, swamps_file, witcher.Swamp, novigrad_map_uri, uri_prefix="Novigrad")

lakes_file = '../InfoFiles/novigrad_lakes.json'
integrate_geo_file(g, lakes_file, witcher.Lake, novigrad_map_uri, uri_prefix="Novigrad")

terrain_file = '../InfoFiles/novigrad_terrain.json'
integrate_geo_file(g, terrain_file, witcher.Terrain, novigrad_map_uri, uri_prefix="Novigrad")

roads_file = '../InfoFiles/novigrad_roads.json'
integrate_geo_file(g, roads_file, witcher.Road, novigrad_map_uri, uri_prefix="Novigrad")

cities_file = '../InfoFiles/novigrad_cities.json'
integrate_geo_file(g, cities_file, witcher.City, novigrad_map_uri, name_attribute='name')

# 4. Define control points for auto-calibration and calculate the transformation matrix
if gis_control_data:
    gis_center, gis_top_right, gis_top_left = gis_control_data
    
    # This is an approximation of the game map's Y extent (might need to change)
    game_map_y_extent = 3000.0 # Approximate Y extent of the game map in-game coordinates (couldn't find actual value)
    game_map_x_extent = game_map_y_extent * 0.906  # Aspect ratio of the GIS map (approximately) - Coul  

    # We now create the control points automatically
    game_control_points = [
        (-890.57, 2585.09),  # In-game top-left
        (2763.86, -1424.50),   # In-game bottom-right
        (-890.57, -1424.50), # In-game bottom-left
        (2763.86, 2585.09)  # In-game top-right
    ]
    gis_control_points = [
        (21.0036502117724, -21.0036501982966), # top left corner of playable area 
        (615.670143636147, -677.368416076594), # bottom right corner of playable area
        (21.0036502117724, -677.368416076594), # bottom left corner of playable area
        (615.670143636147, -21.0036501982966)  # top right corner of playable area
    ]
    
    print("\n--- Auto-Calibrating Using Control Points ---")
    print(f"Game Control Points: {game_control_points}")
    print(f"GIS Control Points: {gis_control_points}")

    transformation_matrix = calculate_affine_transform(game_control_points, gis_control_points)
 
# 5. Integrate and Spatially Link Map Pins using the calculated matrix
mappins_xml_file = '../InfoFiles/MapPins.xml'
integrate_map_pins(g, mappins_xml_file, transformation_matrix)

# ——————————————————————————————
# 5. Save Final RDF Output
# ——————————————————————————————

output_file = '../RDF/main_linked_geo.n3'
g.serialize(output_file, format='n3')

print("\n-------------------------------------------")
print(f"Processing complete.")
print(f"Generated {len(g)} triples.")
print(f"Final linked RDF graph saved to: {output_file}")