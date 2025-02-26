
########################## FINDING MAPPING TYPES BY WORLD ####################################################
# import xml.etree.ElementTree as ET

# def write_mappin_types_by_world(xml_file, output_file):
#     try:
#         # Parse the XML file
#         tree = ET.parse(xml_file)
#         root = tree.getroot()

#         # Dictionary to store mappin types by world
#         world_mappin_types = {}

#         # Iterate through all <world> elements
#         for world in root.findall('world'):
#             world_name = world.get('name')
#             world_code = world.get('code')

#             # Initialize a set to store mappin types for this world
#             mappin_types = set()

#             # Iterate through all <mappin> elements within this <world>
#             for mappin in world.findall('mappin'):
#                 mappin_type = mappin.get('type')
#                 if mappin_type:
#                     mappin_types.add(mappin_type)

#             # Store the mappin types for this world
#             world_mappin_types[(world_name, world_code)] = mappin_types

#         # Write mappin types categorized by world to the output file
#         with open(output_file, 'w') as f:
#             for (world_name, world_code), types in world_mappin_types.items():
#                 f.write(f"World: {world_name} (Code: {world_code})\n")
#                 if types:
#                     f.write("Mappin types found:\n")
#                     for mappin_type in sorted(types):
#                         f.write(f"- {mappin_type}\n")
#                 else:
#                     f.write("No mappin types found.\n")
#                 f.write("\n")  # Add a blank line between worlds

#         print(f"Output written to {output_file}")

#     except ET.ParseError as e:
#         print(f"Error parsing XML file: {e}")
#     except FileNotFoundError:
#         print(f"Error: File '{xml_file}' not found.")

# # Run the script
# if __name__ == "__main__":
#     xml_file = "../InfoFiles/MapPins.xml"  # Replace with your XML file path
#     output_file = "../InfoFiles/MappinTypes.txt"  # Output file name
#     write_mappin_types_by_world(xml_file, output_file)


################################### FINDING DISTINCT MAPPING TYPES #########################################################
import xml.etree.ElementTree as ET

def find_distinct_mappin_types(xml_file, output_file):
    try:
        # Parse the XML file
        tree = ET.parse(xml_file)
        root = tree.getroot()

        # Use a set to store distinct mappin types
        distinct_mappin_types = set()

        # Iterate through all <mappin> elements in the file
        for mappin in root.findall('.//mappin'):  # Find all <mappin> elements at any level
            mappin_type = mappin.get('type')
            if mappin_type:
                distinct_mappin_types.add(mappin_type)

        # Write distinct mappin types to the output file
        with open(output_file, 'w') as f:
            if distinct_mappin_types:
                f.write("Distinct mappin types found:\n")
                for mappin_type in sorted(distinct_mappin_types):
                    f.write(f"- {mappin_type}\n")
            else:
                f.write("No mappin types found.\n")

        print(f"Distinct mappin types written to {output_file}")

    except ET.ParseError as e:
        print(f"Error parsing XML file: {e}")
    except FileNotFoundError:
        print(f"Error: File '{xml_file}' not found.")

# Run the script
if __name__ == "__main__":
    xml_file = "../InfoFiles/MapPins.xml"  # Replace with your XML file path
    output_file = "../InfoFiles/Distinct_Mappin_Types.txt"  # Output file name
    find_distinct_mappin_types(xml_file, output_file)