import xml.etree.ElementTree as ET
import os

# Define the input XML file and output directory
input_file = 'witcher_pages_current.xml'
output_dir = 'output_namespaces/'

# Create the output directory if it doesn't exist
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Define the namespaces you want to extract (e.g., 14, 420, 290)
target_namespaces = {15}  # Add or remove keys as needed

# Initialize a dictionary to store file handles for each namespace
namespace_files = {}

# Parse the XML file
context = ET.iterparse(input_file, events=('start', 'end'))
context = iter(context)
event, root = next(context)

# Counter for debugging
page_count = 0

# Iterate through the XML
for event, elem in context:
    if event == 'end' and elem.tag == '{http://www.mediawiki.org/xml/export-0.11/}page':
        page_count += 1
        # Extract the namespace key
        ns_elem = elem.find('{http://www.mediawiki.org/xml/export-0.11/}ns')
        if ns_elem is not None:
            try:
                ns_key = int(ns_elem.text)  # Ensure the namespace key is an integer
            except ValueError:
                print(f"Skipping page {page_count}: Invalid namespace key '{ns_elem.text}'")
                continue

            # Check if the namespace is in the target list
            if ns_key in target_namespaces:
                # Get the page title and content
                title_elem = elem.find('{http://www.mediawiki.org/xml/export-0.11/}title')
                revision_elem = elem.find('{http://www.mediawiki.org/xml/export-0.11/}revision')
                if revision_elem is not None:
                    text_elem = revision_elem.find('{http://www.mediawiki.org/xml/export-0.11/}text')

                    if title_elem is not None and text_elem is not None:
                        title = title_elem.text
                        content = text_elem.text

                        # Open a file for the namespace if it doesn't exist
                        if ns_key not in namespace_files:
                            namespace_files[ns_key] = open(f'{output_dir}/namespace_{ns_key}.xml', 'w', encoding='utf-8')
                            namespace_files[ns_key].write('<pages>\n')

                        # Write the page to the corresponding file
                        namespace_files[ns_key].write(f'<page>\n')
                        namespace_files[ns_key].write(f'  <title>{title}</title>\n')
                        namespace_files[ns_key].write(f'  <ns>{ns_key}</ns>\n')
                        namespace_files[ns_key].write(f'  <text>{content}</text>\n')
                        namespace_files[ns_key].write(f'</page>\n')
                    else:
                        print(f"Skipping page {page_count}: Missing <title> or <text> element")
                else:
                    print(f"Skipping page {page_count}: Missing <revision> element")
            else:
                print(f"Skipping page {page_count}: Namespace {ns_key} not in target namespaces")
        else:
            print(f"Skipping page {page_count}: Missing <ns> element")

        # Clear the element from memory to save space
        elem.clear()
        root.clear()

# Close all files
for file in namespace_files.values():
    file.write('</pages>\n')
    file.close()

print(f"Pages have been extracted and saved to {output_dir}.")