import xml.etree.ElementTree as ET

# Define namespaces
namespaces = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "witcher": "http://example.org/witcher/ontology#",
    "geo": "http://www.opengis.net/ont/geosparql#",
}

def sanitize_name(value):
    """Replace spaces with underscores for RDF compatibility."""
    return value.replace(" ", "_") if value else "Unknown_Mappin"

def convert_xml_to_rdf(xml_file, output_file):
    try:
        # Parse the XML file
        tree = ET.parse(xml_file)
        root = tree.getroot()

        # Open the output .n3 file
        with open(output_file, 'w') as f:
            # Write prefixes
            for prefix, uri in namespaces.items():
                f.write(f"@prefix {prefix}: <{uri}> .\n")
            f.write("\n")

            # Iterate through all <world> elements
            for world in root.findall('world'):
                world_name = world.get('name')
                world_code = world.get('code')

                # Iterate through all <mappin> elements within this <world>
                for mappin in world.findall('mappin'):
                    mappin_type = mappin.get('type')
                    name = mappin.find('name').text if mappin.find('name') is not None else None
                    position = mappin.find('position')
                    x = position.get('x')
                    y = position.get('y')
                    internalname = mappin.find('internalname').text if mappin.find('internalname') is not None else None

                    # Use internalname if available, otherwise use name
                    instance_name = sanitize_name(internalname if internalname else name)

                    # Create WKT literal for the point
                    wkt_point = f"POINT ({x} {y})"

                    # Write RDF triples
                    f.write(f"witcher:{instance_name} a witcher:{mappin_type} ;\n")
                    f.write(f'    witcher:hasName "{name}"^^xsd:string ;\n')
                    f.write(f'    witcher:hasInternalName "{internalname}"^^xsd:string ;\n')
                    f.write(f'    witcher:locatedInWorld "{world_name} ({world_code})"^^xsd:string ;\n')
                    f.write(f'    geo:hasGeometry [ a geo:Geometry ; geo:asWKT "{wkt_point}"^^geo:wktLiteral ] .\n\n')

        print(f"RDF data written to {output_file}")

    except ET.ParseError as e:
        print(f"Error parsing XML file: {e}")
    except FileNotFoundError:
        print(f"Error: File '{xml_file}' not found.")

# Run the script
if __name__ == "__main__":
    xml_file = "../InfoFiles/MapPins.xml"  # Replace with your XML file path
    output_file = "../RDF/MapPins.n3"  # Output file name
    convert_xml_to_rdf(xml_file, output_file)
